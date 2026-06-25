from sqlalchemy.orm import Session

from app.db.models import AgentSession


def get_or_create_agent_session(
    db: Session,
    user_id: str
) -> AgentSession:
    session = (
        db.query(AgentSession)
        .filter(AgentSession.user_id == user_id)
        .first()
    )

    if session:
        return session

    session = AgentSession(
        user_id=user_id,
        current_scenario="idle",
        current_step=None,
        draft_data={},
        is_active=True,
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def update_agent_session(
    db: Session,
    session: AgentSession,
    current_scenario: str | None = None,
    current_step: str | None = None,
    draft_data: dict | None = None,
    is_active: bool | None = None,
) -> AgentSession:
    if current_scenario is not None:
        session.current_scenario = current_scenario

    if current_step is not None:
        session.current_step = current_step

    if draft_data is not None:
        session.draft_data = dict(draft_data)

    if is_active is not None:
        session.is_active = is_active

    db.commit()
    db.refresh(session)

    return session


def reset_agent_session(
    db: Session,
    session: AgentSession
) -> AgentSession:
    session.current_scenario = "idle"
    session.current_step = None
    session.draft_data = {}
    session.is_active = True

    db.commit()
    db.refresh(session)

    return session

def set_pending_action(
    db: Session,
    session: AgentSession,
    action_type: str,
    payload: dict,
) -> AgentSession:
    draft_data = dict(session.draft_data or {})

    draft_data["pending_action"] = {
        "type": action_type,
        "payload": payload,
    }

    return update_agent_session(
        db=db,
        session=session,
        current_scenario="awaiting_confirmation",
        current_step="confirm_action",
        draft_data=draft_data,
        is_active=True,
    )


def get_pending_action(session: AgentSession) -> dict | None:
    draft_data = dict(session.draft_data or {})
    pending_action = draft_data.get("pending_action")

    if not isinstance(pending_action, dict):
        return None

    return pending_action