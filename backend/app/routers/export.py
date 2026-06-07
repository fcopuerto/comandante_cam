"""
Export job routes.
"""
import uuid
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.camera import Page
from app.schemas.recording import ExportCreate, ExportJobResponse
import app.services.export_service as export_svc

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("", response_model=ExportJobResponse, status_code=status.HTTP_201_CREATED)
async def create_export(
    body: ExportCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("recordings:export")),
) -> ExportJobResponse:
    try:
        return await export_svc.create_export_job(db, body, acting_user, request)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("", response_model=Page[ExportJobResponse])
async def list_exports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("recordings:export")),
) -> Page[ExportJobResponse]:
    jobs, total = await export_svc.list_export_jobs(db, acting_user, page, page_size)
    return Page(
        items=jobs,
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.get("/{job_id}", response_model=ExportJobResponse)
async def get_export(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("recordings:export")),
) -> ExportJobResponse:
    _validate_job_id(job_id)
    try:
        return await export_svc.get_export_status(db, job_id, acting_user, request)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/{job_id}/download")
async def download_export(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("recordings:export")),
) -> StreamingResponse:
    _validate_job_id(job_id)
    try:
        return await export_svc.stream_export_file(db, job_id, acting_user, request)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def _validate_job_id(job_id: str) -> None:
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Export job {job_id} not found")
