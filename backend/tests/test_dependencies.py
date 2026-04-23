from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.infrastructure.security.dependencies import get_current_user
from app.infrastructure.security.jwt import create_access_token


@pytest.mark.asyncio
async def test_get_current_user_valid_token():
    user_id = uuid.uuid4()
    token = create_access_token(subject=str(user_id))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    fake_user = MagicMock()
    fake_user.id = user_id
    fake_user.is_active = True

    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_user

    fake_session = AsyncMock()
    fake_session.execute.return_value = fake_result

    user = await get_current_user(token=credentials, session=fake_session)
    assert user.id == user_id


@pytest.mark.asyncio
async def test_get_current_user_invalid_token():
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.token")
    fake_session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=credentials, session=fake_session)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_inactive_user():
    user_id = uuid.uuid4()
    token = create_access_token(subject=str(user_id))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    fake_user = MagicMock()
    fake_user.id = user_id
    fake_user.is_active = False

    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_user

    fake_session = AsyncMock()
    fake_session.execute.return_value = fake_result

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=credentials, session=fake_session)
    assert exc_info.value.status_code == 401
