from datetime import datetime, timezone
from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    username = db.Column(db.String(24), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default='USER', index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    refresh_sessions = db.relationship('RefreshSession', back_populates='user', cascade='all, delete-orphan')
    favourites = db.relationship('Favourite', back_populates='user', cascade='all, delete-orphan')


class RefreshSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    user = db.relationship('User', back_populates='refresh_sessions')


class Competition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    country = db.Column(db.String(80))
    logo_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    favourites = db.relationship('Favourite', back_populates='competition', cascade='all, delete-orphan')


class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    country = db.Column(db.String(80))
    logo_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    favourites = db.relationship('Favourite', back_populates='team', cascade='all, delete-orphan')


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    competition_id = db.Column(db.Integer, index=True)
    home_team_id = db.Column(db.Integer)
    away_team_id = db.Column(db.Integer)
    kickoff_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    status = db.Column(db.String(24), nullable=False, default='SCHEDULED')
    home_score = db.Column(db.Integer)
    away_score = db.Column(db.Integer)
    streams = db.relationship('Stream', back_populates='match', cascade='all, delete-orphan', foreign_keys='Stream.match_external_id', primaryjoin='Match.external_id == Stream.match_external_id')


class Stream(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_external_id = db.Column(db.Integer, db.ForeignKey('match.external_id', ondelete='CASCADE'), nullable=False, index=True)
    competition = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(2000), nullable=False)
    stream_type = db.Column(db.String(8), nullable=False)
    provider = db.Column(db.String(100), nullable=False)
    authorization_reference = db.Column(db.String(500), nullable=False)
    geographic_restrictions = db.Column(db.JSON, nullable=False, default=list)
    available = db.Column(db.Boolean, nullable=False, default=True, index=True)
    starts_at = db.Column(db.DateTime(timezone=True))
    ends_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    match = db.relationship('Match', back_populates='streams', foreign_keys=[match_external_id], primaryjoin='Match.external_id == Stream.match_external_id')


class Favourite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    target_type = db.Column(db.String(16), nullable=False)
    target_external_id = db.Column(db.Integer, nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id', ondelete='CASCADE'))
    competition_id = db.Column(db.Integer, db.ForeignKey('competition.id', ondelete='CASCADE'))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    user = db.relationship('User', back_populates='favourites')
    team = db.relationship('Team', back_populates='favourites')
    competition = db.relationship('Competition', back_populates='favourites')
    __table_args__ = (db.UniqueConstraint('user_id', 'target_type', 'target_external_id', name='uq_user_favourite_target'), db.Index('ix_user_favourites_created', 'user_id', 'created_at'))
