"""SSH Server management service."""
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models.remote import SSHServer
from app.core.security import encrypt_secret, decrypt_secret

logger = logging.getLogger(__name__)


class SSHServerService:

    def register(
        self,
        user_id: int,
        name: str,
        host: str,
        username: str,
        key_path: str,
        passphrase: str,
        gpu_type: str,
        scheduler_type: str,
        db: Session,
    ) -> SSHServer:
        if not name or len(name) > 100:
            raise HTTPException(422, detail="Server name must be between 1 and 100 characters.")

        server = SSHServer(
            user_id=user_id,
            name=name,
            host=host,
            username=username,
            encrypted_key_path=encrypt_secret(key_path),
            encrypted_passphrase=encrypt_secret(passphrase) if passphrase else None,
            gpu_type=gpu_type,
            scheduler_type=scheduler_type,
        )
        db.add(server)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, detail="An SSH server with this name already exists.")
        db.refresh(server)
        logger.info("Registered SSH server '%s' for user %d", name, user_id)
        return server

    def list_servers(self, user_id: int, db: Session) -> list[SSHServer]:
        return db.query(SSHServer).filter_by(user_id=user_id).all()

    def delete(self, server_id: int, user_id: int, db: Session) -> None:
        server = db.query(SSHServer).filter_by(id=server_id, user_id=user_id).first()
        if not server:
            raise HTTPException(404, detail="SSH server not found.")
        db.delete(server)
        db.commit()
        logger.info("Deleted SSH server %d for user %d", server_id, user_id)

    def health_check_commands(self, server_id: int, user_id: int, db: Session) -> dict[str, str]:
        server = db.query(SSHServer).filter_by(id=server_id, user_id=user_id).first()
        if not server:
            raise HTTPException(404, detail="SSH server not found.")
        # Use $SSH_KEY_PATH placeholder — never expose decrypted key
        ping_cmd = f"ssh -i $SSH_KEY_PATH {server.username}@{server.host} 'echo OK'"
        gpu_cmd = (
            f"ssh -i $SSH_KEY_PATH {server.username}@{server.host} "
            f"'nvidia-smi --query-gpu=name,memory.free --format=csv'"
        )
        return {"ping_cmd": ping_cmd, "gpu_cmd": gpu_cmd}


ssh_server_service = SSHServerService()
