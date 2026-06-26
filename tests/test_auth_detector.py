"""认证系统自动探测器测试"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from requests import Response

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from auth.detector import _identify_system, _is_normal_response, detect_auth_system
from auth.base import AuthSystemType


def _make_response(status_code=200, text="", url="http://example.com"):
    r = Response()
    r.status_code = status_code
    r._content = text.encode()
    r.url = url
    return r


class TestIdentifySystem:
    """URL/内容识别测试"""

    def test_drcom_by_self_sso_login(self):
        assert _identify_system("http://172.20.30.2:8080/Self/sso_login", "") == AuthSystemType.DRCOM

    def test_drcom_by_cas_login(self):
        assert _identify_system("https://sso.dlut.edu.cn/cas/login?service=xxx", "") == AuthSystemType.DRCOM

    def test_drcom_by_self_login(self):
        assert _identify_system("http://172.20.30.2:8080/Self/login/", "") == AuthSystemType.DRCOM

    def test_ruijie_by_eportal(self):
        assert _identify_system("http://10.10.10.10/eportal/index.jsp", "") == AuthSystemType.RUIJIE

    def test_srun_by_url(self):
        assert _identify_system("http://10.0.0.1/srun_portal_pc?ac_id=1", "") == AuthSystemType.SRUN

    def test_srun_by_content(self):
        content = '<html><body>深澜网络科技 srunportal</body></html>'
        assert _identify_system("http://10.0.0.1/auth", content) == AuthSystemType.SRUN

    def test_portal_by_form_with_password(self):
        content = '<html><form action="/login"><input type="password" name="pwd"><input type="text" name="user"></form></html>'
        assert _identify_system("http://10.0.0.1/auth", content) == AuthSystemType.PORTAL

    def test_unknown_for_empty(self):
        assert _identify_system("http://10.0.0.1/random", "") == AuthSystemType.UNKNOWN


class TestIsNormalResponse:
    """正常响应判断测试"""

    def test_msftconnecttest_normal(self):
        r = _make_response(200, "Microsoft Connect Test", "http://www.msftconnecttest.com/connecttest.txt")
        assert _is_normal_response(r, "http://www.msftconnecttest.com/connecttest.txt") is True

    def test_generate_204_normal(self):
        r = _make_response(204, "", "http://connect.rom.miui.com/generate_204")
        assert _is_normal_response(r, "http://connect.rom.miui.com/generate_204") is True

    def test_generate_204_redirected_to_auth_is_not_normal(self):
        r = _make_response(200, "<html>Please login</html>", "http://172.20.30.2:8080/Self/login")
        assert _is_normal_response(r, "http://connect.rom.miui.com/generate_204") is False

    def test_redirect_to_auth_page_is_not_normal(self):
        r = _make_response(200, "<html>CAS login</html>", "https://sso.dlut.edu.cn/cas/login")
        assert _is_normal_response(r, "http://www.msftconnecttest.com/connecttest.txt") is False
