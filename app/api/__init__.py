from fastapi import APIRouter
from app.api import topics, papers, pipeline_ops, auth, labs, github, profiles, lab_homepage, news, admin, slides, cost
from app.api import ssh_servers, remote_ops
from app.api.profiles import public_router as profiles_public_router
from app.api import minimax

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(labs.router, prefix="/labs", tags=["labs"])
router.include_router(topics.router, prefix="/topics", tags=["topics"])
router.include_router(papers.router, prefix="/papers", tags=["papers"])
router.include_router(pipeline_ops.router, tags=["pipeline"])
router.include_router(github.router, tags=["github"])
router.include_router(profiles.router, prefix="/users", tags=["profiles"])
router.include_router(profiles_public_router)
router.include_router(lab_homepage.router, prefix="/labs", tags=["lab-homepage"])
router.include_router(news.router, tags=["news"])
router.include_router(admin.router, tags=["admin"])
router.include_router(slides.router, prefix="/labs", tags=["slides"])
router.include_router(ssh_servers.router, tags=["ssh-servers"])
router.include_router(remote_ops.router, tags=["remote-execution"])
router.include_router(cost.router, tags=["cost"])

# MiniMax management endpoints (config, quick checks)
router.include_router(minimax.router, tags=["minimax"])
