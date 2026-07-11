from unittest.mock import Mock, patch

from auth.base import AuthSystemType
from campus_auth import CampusAuth


@patch("campus_auth.create_auth_instance")
@patch("campus_auth.detect_auth_system")
def test_online_auto_detection_does_not_lock_to_drcom(detect, create):
    detect.return_value = (AuthSystemType.UNKNOWN, "", "")
    router = CampusAuth()

    assert router._ensure_auth() is None
    create.assert_not_called()


@patch("campus_auth.create_auth_instance")
@patch("campus_auth.detect_auth_system")
def test_auto_detection_retries_until_portal_is_visible(detect, create):
    portal = Mock()
    detect.side_effect = [
        (AuthSystemType.UNKNOWN, "", ""),
        (AuthSystemType.PORTAL, "http://portal/login", "<form></form>"),
    ]
    create.return_value = portal
    router = CampusAuth()

    assert router._ensure_auth() is None
    assert router._ensure_auth() is portal
    create.assert_called_once()
