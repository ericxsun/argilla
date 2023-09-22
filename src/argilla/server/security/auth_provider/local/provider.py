#  coding=utf-8
#  Copyright 2021-present, the Recognai S.L. team.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, SecurityScopes
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from argilla.server import helpers
from argilla.server.contexts import accounts
from argilla.server.database import get_async_db
from argilla.server.errors import UnauthorizedError
from argilla.server.models import User
from argilla.server.security.auth_provider.base import AuthProvider, api_key_header
from argilla.server.settings import settings

from .settings import Settings

SECURITY_TOKEN_PATH = "/security/token"


def public_oauth_token_url():
    """The final public token url used for openapi doc setup"""
    return f"{settings.base_url}api{SECURITY_TOKEN_PATH}"


_oauth2_scheme = OAuth2PasswordBearer(tokenUrl=public_oauth_token_url(), auto_error=False)


class LocalAuthProvider(AuthProvider):
    def __init__(self, settings: Settings):
        self.router = APIRouter(tags=["security"])
        self.settings = settings

        # TODO: maybe it's better if we move this endpoint to apis/v0/handlers

    def create_access_token(self, username: str) -> str:
        """
        Creates an access token

        Parameters
        ----------
        username:
            The user name
        expires_delta:
            Token expiration

        Returns
        -------
            An access token string
        """
        to_encode = {"sub": username}

        if self.settings.token_expiration_in_minutes is not None:
            expires_delta = timedelta(minutes=self.settings.token_expiration_in_minutes)
            to_encode["exp"] = datetime.utcnow() + expires_delta

        return jwt.encode(to_encode, self.settings.secret_key, algorithm=self.settings.algorithm)

    async def fetch_token_user(self, db: AsyncSession, token: str) -> Optional[User]:
        """
        Fetch the user for a given access token

        Parameters
        ----------
        token:
            The access token

        Returns
        -------
            An User instance if a valid token was provided. None otherwise
        """
        try:
            payload = jwt.decode(token, self.settings.secret_key, algorithms=[self.settings.algorithm])
            username: str = payload.get("sub")

            if username:
                user = await accounts.get_user_by_username(db, username)
                return user

        except JWTError:
            return None

    async def get_current_user(
        self,
        security_scopes: SecurityScopes,
        db: AsyncSession = Depends(get_async_db),
        api_key: Optional[str] = Depends(api_key_header),
        token: Optional[str] = Depends(_oauth2_scheme),
    ) -> User:
        user = None

        if api_key:
            user = await accounts.get_user_by_api_key(db, api_key)
        elif token:
            user = await self.fetch_token_user(db, token)

        if user is None:
            raise UnauthorizedError()

        return user


def create_local_auth_provider():
    settings = Settings()

    return LocalAuthProvider(settings=settings)
