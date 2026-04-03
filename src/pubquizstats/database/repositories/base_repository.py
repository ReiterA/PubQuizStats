"""Base repository class."""

from typing import TypeVar, Generic, List, Optional
from sqlalchemy.orm import Session

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Base repository for database operations."""

    def __init__(self, session: Session, model_class: type[T]):
        """Initialize repository."""
        self.session = session
        self.model_class = model_class

    def create(self, obj: T) -> T:
        """Create and return an object."""
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj

    def get_by_id(self, id: int) -> Optional[T]:
        """Get object by ID."""
        return self.session.query(self.model_class).filter_by(id=id).first()

    def update(self, id: int, **kwargs) -> Optional[T]:
        """Update object by ID."""
        obj = self.get_by_id(id)
        if obj:
            for key, value in kwargs.items():
                setattr(obj, key, value)
            self.session.commit()
            self.session.refresh(obj)
        return obj

    def delete(self, id: int) -> bool:
        """Delete object by ID."""
        obj = self.get_by_id(id)
        if obj:
            self.session.delete(obj)
            self.session.commit()
            return True
        return False

    def list_all(self) -> List[T]:
        """List all objects."""
        return self.session.query(self.model_class).all()
