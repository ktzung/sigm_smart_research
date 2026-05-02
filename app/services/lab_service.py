"""Lab management: create, invite, accept, remove, RBAC, usage stats."""
import hashlib
import logging
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit import UsageStat
from app.models.lab import Lab, LabInvitation, LabMember
from app.models.auth import User

logger = logging.getLogger(__name__)
_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731

ROLE_HIERARCHY: dict[str, int] = {
    "professor": 4,
    "phd_student": 3,
    "master_student": 2,
    "undergraduate_student": 1,
}
VALID_ROLES: list[str] = ["professor", "phd_student", "master_student", "undergraduate_student"]


class LabService:
    """Handles lab creation, member management, invitations, and RBAC."""

    # ── Create lab ────────────────────────────────────────────────────────────

    def create_lab(self, name: str, description: str | None, owner: User, db: Session) -> Lab:
        """Create a Lab and automatically add owner as professor."""
        lab = Lab(name=name, description=description, owner_id=owner.id)
        db.add(lab)
        db.flush()
        member = LabMember(lab_id=lab.id, user_id=owner.id, role="professor")
        db.add(member)
        db.commit()
        db.refresh(lab)
        logger.info("Lab created: %s (id=%d) by user %d", lab.name, lab.id, owner.id)
        return lab

    # ── Invite member ─────────────────────────────────────────────────────────

    def invite_member(
        self, lab_id: int, email: str, role: str, inviter: User, db: Session
    ) -> LabInvitation:
        """Check inviter is professor, create invitation token, send/log email."""
        if role not in VALID_ROLES:
            raise HTTPException(422, detail=f"Invalid role. Valid roles: {VALID_ROLES}")
        self._require_professor(lab_id, inviter.id, db)

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        inv = LabInvitation(
            lab_id=lab_id,
            email=email.lower(),
            role=role,
            token_hash=token_hash,
            expires_at=_utcnow() + timedelta(days=7),
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        # Attach raw token so callers can return it to the invitee
        inv._raw_token = raw_token  # type: ignore[attr-defined]
        _send_invitation_email(email, raw_token, lab_id)
        logger.info("Invitation sent: lab=%d email=%s role=%s", lab_id, email, role)
        return inv

    # ── Accept invitation ─────────────────────────────────────────────────────

    def accept_invitation(self, token: str, user: User, db: Session) -> LabMember:
        """Validate token (not expired, not accepted), create LabMember, mark accepted."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        inv = db.query(LabInvitation).filter_by(token_hash=token_hash).first()
        if not inv or inv.accepted or inv.expires_at < _utcnow():
            raise HTTPException(400, detail="Invitation invalid or expired")

        existing = db.query(LabMember).filter_by(lab_id=inv.lab_id, user_id=user.id).first()
        if existing:
            raise HTTPException(409, detail="Already a member of this lab")

        member = LabMember(lab_id=inv.lab_id, user_id=user.id, role=inv.role)
        db.add(member)
        inv.accepted = True
        db.commit()
        db.refresh(member)
        return member

    # ── Remove member ─────────────────────────────────────────────────────────

    def remove_member(self, lab_id: int, user_id: int, requester: User, db: Session) -> None:
        """Check requester is professor, delete LabMember."""
        self._require_professor(lab_id, requester.id, db)
        if user_id == requester.id:
            raise HTTPException(400, detail="Cannot remove yourself from the lab")
        member = db.query(LabMember).filter_by(lab_id=lab_id, user_id=user_id).first()
        if not member:
            raise HTTPException(404, detail="Member not found")
        db.delete(member)
        db.commit()

    # ── Usage stats ───────────────────────────────────────────────────────────

    def get_usage_stats(self, lab_id: int, month: date, db: Session) -> dict:
        """Aggregate UsageStat for all members in the lab for the given month."""
        member_user_ids = (
            db.query(LabMember.user_id).filter(LabMember.lab_id == lab_id).subquery()
        )
        row = (
            db.query(
                func.coalesce(func.sum(UsageStat.topics_created), 0).label("topics_created"),
                func.coalesce(func.sum(UsageStat.pipeline_runs), 0).label("pipeline_runs"),
                func.coalesce(func.sum(UsageStat.papers_ingested), 0).label("papers_ingested"),
            )
            .filter(
                UsageStat.user_id.in_(member_user_ids),
                UsageStat.month == month,
            )
            .one()
        )
        return {
            "lab_id": lab_id,
            "month": month.isoformat(),
            "topics_created": int(row.topics_created),
            "pipeline_runs": int(row.pipeline_runs),
            "papers_ingested": int(row.papers_ingested),
        }

    # ── Role permission check ─────────────────────────────────────────────────

    def check_role_permission(self, member: LabMember, required_role: str) -> bool:
        """Return True if member's role meets or exceeds required_role in hierarchy."""
        return ROLE_HIERARCHY.get(member.role, 0) >= ROLE_HIERARCHY.get(required_role, 0)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_member(self, lab_id: int, user_id: int, db: Session) -> LabMember | None:
        return db.query(LabMember).filter_by(lab_id=lab_id, user_id=user_id).first()

    def require_min_role(
        self, lab_id: int, user_id: int, required_role: str, db: Session
    ) -> LabMember:
        member = self.get_member(lab_id, user_id, db)
        if not member:
            raise HTTPException(403, detail="Not a member of this lab")
        if not self.check_role_permission(member, required_role):
            raise HTTPException(403, detail=f"Required role: {required_role}")
        return member

    def _require_professor(self, lab_id: int, user_id: int, db: Session) -> LabMember:
        return self.require_min_role(lab_id, user_id, "professor", db)


# ── Module-level singleton + backward-compatible function aliases ─────────────

lab_service = LabService()


def create_lab(name: str, description: str | None, owner: User, db: Session) -> Lab:
    return lab_service.create_lab(name, description, owner, db)


def invite_member(
    lab_id: int, email: str, role: str, inviter: User, db: Session
) -> LabInvitation:
    return lab_service.invite_member(lab_id, email, role, inviter, db)


def accept_invitation(raw_token: str, user: User, db: Session) -> LabMember:
    return lab_service.accept_invitation(raw_token, user, db)


def remove_member(lab_id: int, user_id: int, requester: User, db: Session) -> None:
    return lab_service.remove_member(lab_id, user_id, requester, db)


def get_usage_stats(lab_id: int, month: date, db: Session) -> dict:
    return lab_service.get_usage_stats(lab_id, month, db)


def get_member(lab_id: int, user_id: int, db: Session) -> LabMember | None:
    return lab_service.get_member(lab_id, user_id, db)


def check_role_permission(member: LabMember, required_role: str) -> bool:
    return lab_service.check_role_permission(member, required_role)


def require_min_role(
    lab_id: int, user_id: int, required_role: str, db: Session
) -> LabMember:
    return lab_service.require_min_role(lab_id, user_id, required_role, db)


# ── Email helper ──────────────────────────────────────────────────────────────

def _send_invitation_email(email: str, raw_token: str, lab_id: int) -> None:
    """Send invitation email; log if SMTP not configured."""
    try:
        from app.core.config import settings
        if not settings.smtp_host:
            logger.info(
                "SMTP not configured. Invitation token for %s (lab=%d): %s",
                email, lab_id, raw_token,
            )
            return
        import smtplib
        from email.mime.text import MIMEText

        accept_url = f"http://localhost:8000/labs/{lab_id}/accept?token={raw_token}"
        msg = MIMEText(f"You have been invited to join a lab.\n\nAccept: {accept_url}\n\nExpires in 7 days.")
        msg["Subject"] = "ChimCanhCut — Lab Invitation"
        msg["From"] = settings.smtp_from
        msg["To"] = email
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
            if settings.smtp_user:
                s.starttls()
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except Exception as exc:
        logger.error("Failed to send invitation email to %s: %s", email, exc)
