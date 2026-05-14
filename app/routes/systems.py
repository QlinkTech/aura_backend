from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.utils.logger_config import logger
from app.utils.env_load import username as us, password as pwd
from app.services.auth_service import create_access_token, get_system_user
from app.routes.system_sub_routes.users import users_router
from app.routes.system_sub_routes.stats import stats_router
from app.routes.system_sub_routes.prompt import prompt_router
from app.routes.system_sub_routes.kb import kb_router
from app.routes.system_sub_routes.resources import resources_router
from app.routes.system_sub_routes.masterclass import masterclass_router
from app.routes.system_sub_routes.notifications import notifications_router

system_router = APIRouter()

_auth = [Depends(get_system_user)]
system_router.include_router(users_router, dependencies=_auth)
system_router.include_router(stats_router, dependencies=_auth)
system_router.include_router(prompt_router, dependencies=_auth)
system_router.include_router(kb_router, dependencies=_auth)
system_router.include_router(resources_router, dependencies=_auth)
system_router.include_router(masterclass_router, dependencies=_auth)
system_router.include_router(notifications_router, dependencies=_auth)


class LoginData(BaseModel):
    username: str
    password: str


@system_router.post("/login")
def login(data: LoginData):
    """Dashboard Login."""
    username = data.username.lower()
    password = data.password
    try:
        if not password or not username:
            logger.warning("Dashboard login attempt with missing credentials")
            return JSONResponse({"success": False, "message": "Invalid Request"}, status_code=401)
        elif username != us or password != pwd:
            logger.warning("Dashboard login failed - invalid credentials", extra={"username": username})
            return JSONResponse({"success": False, "message": "Invalid Username or Password"}, status_code=402)
        else:
            logger.info("Dashboard login successful", extra={"username": username})
            token = create_access_token({"sub": username, "role": "system"})
            return JSONResponse({"success": True, "access_token": token, "token_type": "bearer"}, status_code=201)
    except Exception as e:
        logger.error("Dashboard login error", extra={"username": username, "error": str(e)})
        return JSONResponse({"success": False, "message": str(e)}, status_code=501)
