import pytest

import threadvault.configuration
import threadvault.slack.permission

USERS_CLASSIFIED = [('UXXX1', 'owner'), ('UXXX2', 'admin'), ('UXXX3', 'member')]

@pytest.mark.parametrize(('user', 'role'), USERS_CLASSIFIED)
def test_permission_user_role(
    user: str,
    role: threadvault.slack.permission.Role
) -> None:

    settings = threadvault.configuration.load({'THREADVAULT_OWNER_ID': 'UXXX1', 'THREADVAULT_ADMIN_IDS': 'UXXX1,UXXX2'})

    assert threadvault.slack.permission.role(settings, user) == role
