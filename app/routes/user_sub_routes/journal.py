from fastapi import APIRouter, Depends, HTTPException
from app.utils.schema import JournalModel
from app.services.auth_service import get_active_user
from app.core.journal_agent.journal_agent import journal_agent, generate_journal_prompts
from app.services.db.journal_utils import get_journal_logs, get_journal_log_by_id, delete_journal_log
from app.services.db.pinecone_utils import delete_record_by_id, pinecone_journal_namespace
from app.utils.logger_config import logger

journal_router = APIRouter()


@journal_router.get("/journal-prompts")
def get_journal_prompts(current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Journal prompts request", extra={"email": email})
    result = generate_journal_prompts(email=email)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"prompts": result["prompts"]}


@journal_router.post("/journal")
def submit_journal(data: JournalModel, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Journal submission received", extra={"email": email})
    result = journal_agent(
        email=email,
        journal_prompt=data.journal_prompt,
        journal_entry=data.journal_entry
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@journal_router.get("/journal-logs")
def list_journal_logs(current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("List journal logs request", extra={"email": email})
    logs = get_journal_logs(email=email)
    return {"logs": logs}


@journal_router.get("/journal-logs/{log_id}")
def get_journal_log(log_id: str, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Get journal log request", extra={"email": email, "log_id": log_id})
    log = get_journal_log_by_id(email=email, log_id=log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Journal log not found")
    return log


@journal_router.delete("/journal-logs/{log_id}")
def remove_journal_log(log_id: str, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Delete journal log request", extra={"email": email, "log_id": log_id})
    deleted = delete_journal_log(email=email, log_id=log_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Journal log not found")
    delete_record_by_id(record_id=log_id, namespace=pinecone_journal_namespace)
    return {"success": True}
