from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationship
    qr_codes = db.relationship(
        'QRCode',
        backref='owner',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def update_last_login(self):
        self.last_login = datetime.now()
        db.session.commit()
    
    def get_stats(self):
        from sqlalchemy import func
        from datetime import timezone
        
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today.replace(day=1)

        # Total QR codes
        total_qr_codes = self.qr_codes.count()

        # Total scans across all QR codes
        total_scans = db.session.query(func.sum(QRCode.scan_count)).filter(
            QRCode.user_id == self.id
        ).scalar() or 0

        # QR codes created this month
        this_month_codes = self.qr_codes.filter(
            QRCode.created_at >= month_start
        ).count()

        # Additional stats
        active = self.qr_codes.filter_by(is_active=True).filter(
            (QRCode.expiry_date == None) | (QRCode.expiry_date > now)
        ).count()

        expired = self.qr_codes.filter(
            QRCode.expiry_date != None,
            QRCode.expiry_date <= now
        ).count()

        inactive = self.qr_codes.filter_by(is_active=False).count()
        
        return {
            'total_qr_codes': total_qr_codes,
            'total_scans': total_scans,
            'this_month_codes': this_month_codes,
            'active': active,
            'expired': expired,
            'inactive': inactive
        }


class QRCode(db.Model):
    __tablename__ = 'qr_codes'
    
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(
        db.String(36),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # QR Data
    data_type = db.Column(db.String(20), nullable=False)
    original_data = db.Column(db.Text, nullable=False)
    encrypted_data = db.Column(db.Text, nullable=True)
    
    # Customization
    foreground_color = db.Column(db.String(7), default='#000000')
    background_color = db.Column(db.String(7), default='#FFFFFF')
    has_logo = db.Column(db.Boolean, default=False)
    logo_path = db.Column(db.String(256), nullable=True)
    
    # File info
    filename = db.Column(db.String(256), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    
    # Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    expiry_date = db.Column(db.DateTime, nullable=True, index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Analytics
    scan_count = db.Column(db.Integer, default=0)
    last_scanned = db.Column(db.DateTime, nullable=True)
    
    @property
    def is_expired(self):
        if self.expiry_date is None:
            return False
        return datetime.now() > self.expiry_date  # ✅ FIXED
    
    @property
    def status(self):
        if not self.is_active:
            return 'inactive'
        elif self.is_expired:
            return 'expired'
        return 'active'
    
    @property
    def status_badge(self):
        status_map = {
            'active': ('Active', 'success'),
            'inactive': ('Inactive', 'secondary'),
            'expired': ('Expired', 'danger')
        }
        return status_map.get(self.status, ('Unknown', 'dark'))
    
    def increment_scan(self):
        self.scan_count += 1
        self.last_scanned = datetime.now()
        db.session.commit()
    
    def to_dict(self):
        return {
            'id': self.id,
            'uid': self.uid,
            'data_type': self.data_type,
            'original_data': self.original_data,
            'is_active': self.is_active,
            'expiry_date': self.expiry_date.isoformat() if self.expiry_date else None,
            'status': self.status,
            'scan_count': self.scan_count,
            'created_at': self.created_at.isoformat()
        }


class ScanLog(db.Model):
    __tablename__ = 'scan_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    qr_code_id = db.Column(db.Integer, db.ForeignKey('qr_codes.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    scanned_data = db.Column(db.Text, nullable=False)
    scan_result = db.Column(db.String(50), nullable=False)
    scanned_at = db.Column(db.DateTime, default=datetime.now)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)