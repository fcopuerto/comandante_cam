"""Minimal ONVIF mock server + WS-Discovery responder."""
import os
import socket
import struct
import threading
import uuid
from flask import Flask, request, Response

CAM_ID   = os.environ.get('CAM_ID', '1')
HOST_IP  = os.environ.get('HOST_IP', '192.168.1.231')
HTTP_PORT = int(os.environ.get('HTTP_PORT', '8081'))
RTSP_URL = os.environ.get('RTSP_URL', f'rtsp://{HOST_IP}:8554/cam1')

app = Flask(__name__)

# ── SOAP helpers ──────────────────────────────────────────────────────────────
NS = '''xmlns:s="http://www.w3.org/2003/05/soap-envelope"
        xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
        xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
        xmlns:tt="http://www.onvif.org/ver10/schema"'''

def envelope(body: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><s:Envelope {NS}><s:Body>{body}</s:Body></s:Envelope>'

def xml(body: str):
    return Response(envelope(body), content_type='application/soap+xml; charset=utf-8')

# ── Device service ─────────────────────────────────────────────────────────────
@app.route('/onvif/device_service', methods=['POST'])
def device_service():
    body = request.data.decode(errors='ignore')

    if 'GetSystemDateAndTime' in body:
        return xml('<tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime>'
                   '<tt:DateTimeType>NTP</tt:DateTimeType>'
                   '</tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse>')

    if 'GetCapabilities' in body:
        return xml(f'''<tds:GetCapabilitiesResponse><tds:Capabilities>
          <tt:Media><tt:XAddr>http://{HOST_IP}:{HTTP_PORT}/onvif/media_service</tt:XAddr></tt:Media>
        </tds:Capabilities></tds:GetCapabilitiesResponse>''')

    if 'GetDeviceInformation' in body:
        return xml(f'''<tds:GetDeviceInformationResponse>
          <tds:Manufacturer>FakeCam</tds:Manufacturer>
          <tds:Model>MockCam-{CAM_ID}</tds:Model>
          <tds:FirmwareVersion>1.0.0</tds:FirmwareVersion>
          <tds:SerialNumber>FC{CAM_ID:0>6}</tds:SerialNumber>
          <tds:HardwareId>1.0</tds:HardwareId>
        </tds:GetDeviceInformationResponse>''')

    if 'GetScopes' in body:
        return xml(f'''<tds:GetScopesResponse>
          <tds:Scopes><tt:ScopeDef>Fixed</tt:ScopeDef>
            <tt:ScopeItem>onvif://www.onvif.org/name/MockCam-{CAM_ID}</tt:ScopeItem>
          </tds:Scopes>
          <tds:Scopes><tt:ScopeDef>Fixed</tt:ScopeDef>
            <tt:ScopeItem>onvif://www.onvif.org/hardware/FakeCam</tt:ScopeItem>
          </tds:Scopes>
        </tds:GetScopesResponse>''')

    # Fallback
    return xml('<s:Fault><s:Code><s:Value>s:Sender</s:Value></s:Code>'
               '<s:Reason><s:Text>Not Implemented</s:Text></s:Reason></s:Fault>'), 400

# ── Media service ──────────────────────────────────────────────────────────────
@app.route('/onvif/media_service', methods=['POST'])
def media_service():
    body = request.data.decode(errors='ignore')

    if 'GetProfiles' in body or 'GetProfile' in body:
        return xml(f'''<trt:GetProfilesResponse>
          <trt:Profiles token="Profile_1" fixed="true">
            <tt:Name>MainStream</tt:Name>
            <tt:VideoSourceConfiguration token="VS1">
              <tt:Name>VS</tt:Name><tt:UseCount>1</tt:UseCount>
              <tt:SourceToken>VS1</tt:SourceToken>
              <tt:Bounds x="0" y="0" width="1280" height="720"/>
            </tt:VideoSourceConfiguration>
            <tt:VideoEncoderConfiguration token="VE1">
              <tt:Name>VE</tt:Name><tt:UseCount>1</tt:UseCount>
              <tt:Encoding>H264</tt:Encoding>
              <tt:Resolution><tt:Width>1280</tt:Width><tt:Height>720</tt:Height></tt:Resolution>
              <tt:RateControl>
                <tt:FrameRateLimit>25</tt:FrameRateLimit>
                <tt:EncodingInterval>1</tt:EncodingInterval>
                <tt:BitrateLimit>2048</tt:BitrateLimit>
              </tt:RateControl>
            </tt:VideoEncoderConfiguration>
          </trt:Profiles>
        </trt:GetProfilesResponse>''')

    if 'GetStreamUri' in body:
        return xml(f'''<trt:GetStreamUriResponse>
          <trt:MediaUri>
            <tt:Uri>{RTSP_URL}</tt:Uri>
            <tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
            <tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
            <tt:Timeout>PT0S</tt:Timeout>
          </trt:MediaUri>
        </trt:GetStreamUriResponse>''')

    if 'GetSnapshotUri' in body:
        return xml(f'''<trt:GetSnapshotUriResponse>
          <trt:MediaUri>
            <tt:Uri>http://{HOST_IP}:{HTTP_PORT}/snapshot.jpg</tt:Uri>
            <tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
            <tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
            <tt:Timeout>PT0S</tt:Timeout>
          </trt:MediaUri>
        </trt:GetSnapshotUriResponse>''')

    if 'GetVideoSources' in body:
        return xml('''<trt:GetVideoSourcesResponse>
          <trt:VideoSources token="VS1">
            <tt:Framerate>25</tt:Framerate>
            <tt:Resolution><tt:Width>1280</tt:Width><tt:Height>720</tt:Height></tt:Resolution>
          </trt:VideoSources>
        </trt:GetVideoSourcesResponse>''')

    return xml('<s:Fault><s:Code><s:Value>s:Sender</s:Value></s:Code>'
               '<s:Reason><s:Text>Not Implemented</s:Text></s:Reason></s:Fault>'), 400

# ── WS-Discovery responder (UDP multicast 239.255.255.250:3702) ────────────────
WSDD_ADDR = ('239.255.255.250', 3702)
DEVICE_UUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, f'fake-cam-{CAM_ID}'))

def _extract_msgid(data: str) -> str:
    import re
    m = re.search(r'<[^>]*MessageID[^>]*>([^<]+)<', data)
    return m.group(1) if m else f'urn:{uuid.uuid4()}'

def ws_discovery_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('', 3702))
        mreq = struct.pack('4sL', socket.inet_aton(WSDD_ADDR[0]), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    except OSError:
        return  # Already bound by another cam instance on same host

    while True:
        try:
            data, addr = sock.recvfrom(65536)
            msg = data.decode('utf-8', errors='ignore')
            if 'Probe' not in msg:
                continue
            if not any(t in msg for t in ('NetworkVideoTransmitter', 'Device', 'Any', '*')):
                continue
            reply = f'''<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <s:Header>
    <a:MessageID>urn:{uuid.uuid4()}</a:MessageID>
    <a:RelatesTo>{_extract_msgid(msg)}</a:RelatesTo>
    <a:To>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:To>
    <a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</a:Action>
  </s:Header>
  <s:Body>
    <d:ProbeMatches>
      <d:ProbeMatch>
        <a:EndpointReference><a:Address>urn:uuid:{DEVICE_UUID}</a:Address></a:EndpointReference>
        <d:Types>dn:NetworkVideoTransmitter</d:Types>
        <d:Scopes>onvif://www.onvif.org/type/video_encoder onvif://www.onvif.org/name/MockCam-{CAM_ID}</d:Scopes>
        <d:XAddrs>http://{HOST_IP}:{HTTP_PORT}/onvif/device_service</d:XAddrs>
        <d:MetadataVersion>1</d:MetadataVersion>
      </d:ProbeMatch>
    </d:ProbeMatches>
  </s:Body>
</s:Envelope>'''
            sock.sendto(reply.encode(), addr)
        except Exception:
            pass

if __name__ == '__main__':
    t = threading.Thread(target=ws_discovery_listener, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=HTTP_PORT)
