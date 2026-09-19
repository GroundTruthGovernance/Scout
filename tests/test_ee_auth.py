from unittest.mock import MagicMock

import pytest

from scout.core.ee_auth import EarthEngineAuth


@pytest.fixture
def mock_ee(tmp_path):
    ee = MagicMock(name="ee")
    ee.oauth.get_credentials_path.return_value = str(tmp_path / "credentials")
    return ee


@pytest.fixture
def auth(mock_ee):
    return EarthEngineAuth(ee_module=mock_ee)


def test_is_authenticated_false_when_no_credentials_file(auth):
    assert auth.is_authenticated() is False


def test_is_authenticated_true_once_file_exists(auth):
    with open(auth.credentials_path(), "w") as f:
        f.write("{}")
    assert auth.is_authenticated() is True


def test_initialize_without_project(auth, mock_ee):
    auth.initialize()
    mock_ee.Initialize.assert_called_once_with()


def test_initialize_with_project(auth, mock_ee):
    auth.initialize(project="my-ee-project")
    mock_ee.Initialize.assert_called_once_with(project="my-ee-project")


def test_authenticate_interactive_calls_ee_authenticate(auth, mock_ee):
    auth.authenticate_interactive()
    mock_ee.Authenticate.assert_called_once_with(auth_mode="notebook")


def test_sign_out_removes_existing_credentials_file(auth):
    path = auth.credentials_path()
    with open(path, "w") as f:
        f.write("{}")
    assert auth.is_authenticated() is True
    auth.sign_out()
    assert auth.is_authenticated() is False


def test_sign_out_is_a_noop_when_nothing_stored(auth):
    auth.sign_out()  # must not raise
    assert auth.is_authenticated() is False
