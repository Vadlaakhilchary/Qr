from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timezone, timedelta
import os
import uuid

from config import Config
from models import db, User, QRCode, ScanLog

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Initialize utilities
from util import DataEncryption, DataValidator, QRGenerator, QRScanner

encryption = DataEncryption()
validator = DataValidator()
qr_generator = QRGenerator()
qr_scanner = QRScanner()

# Ensure directories exist
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(Config.QR_CODES_FOLDER, exist_ok=True)

def get_external_url(endpoint, **kwargs):
    """Generate external URL that works on other devices (uses current request host)."""
    # Build URL using the current request's host
    scheme = request.scheme
    host = request.host
    path = url_for(endpoint, **kwargs)
    return f"{scheme}://{host}{path}"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create tables
with app.app_context():
    db.create_all()

# ==================== AUTH ROUTES ====================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return render_template('login.html')
        
        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated.', 'danger')
                return render_template('login.html')
            
            login_user(user, remember=remember)
            user.update_last_login()
            flash('Welcome back!', 'success')
            
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('dashboard'))
        
        flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        errors = []
        
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        
        if not validator.validate_email(email):
            errors.append('Please enter a valid email address.')
        
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        
        if password != confirm_password:
            errors.append('Passwords do not match.')
        
        if User.query.filter_by(username=username).first():
            errors.append('Username already exists.')
        
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered.')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('register.html')
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ==================== DASHBOARD ====================

@app.route('/dashboard')
@login_required
def dashboard():
    stats = current_user.get_stats()
    recent_qr_codes = current_user.qr_codes.order_by(QRCode.created_at.desc()).limit(5).all()
    
    return render_template('dashboard.html', stats=stats, recent_qr_codes=recent_qr_codes)

# ==================== QR GENERATION ====================

@app.route('/generate', methods=['GET', 'POST'])
@login_required
def generate():
    if request.method == 'POST':
        data_type = request.form.get('data_type', 'text')
        data = request.form.get('data', '').strip()
        foreground = request.form.get('foreground_color', '#000000')
        background = request.form.get('background_color', '#FFFFFF')
        expiry_days = request.form.get('expiry_days', '')
        encrypt_data = request.form.get('encrypt_data', False)
        
        # Validation
        if not data:
            flash('Please enter data for the QR code.', 'danger')
            return render_template('generate.html')
        
        if data_type == 'url' and not validator.validate_url(data):
            flash('Please enter a valid URL (include http:// or https://).', 'danger')
            return render_template('generate.html')
        
        if not validator.validate_hex_color(foreground) or not validator.validate_hex_color(background):
            flash('Invalid color format.', 'danger')
            return render_template('generate.html')
        
        # Handle logo upload
        logo_path = None
        has_logo = False
        if 'logo' in request.files:
            logo_file = request.files['logo']
            if logo_file and logo_file.filename and validator.allowed_file(logo_file.filename):
                logo_filename = f"logo_{uuid.uuid4().hex}_{secure_filename(logo_file.filename)}"
                logo_path = os.path.join(Config.UPLOAD_FOLDER, logo_filename)
                logo_file.save(logo_path)
                has_logo = True
        
        # Create QR code record
        uid = str(uuid.uuid4())
        
        # Encrypt data if requested
        encrypted_data = None
        if encrypt_data:
            encrypted_data = encryption.encrypt(data)
        
        # Calculate expiry date
        expiry_date = None
        if expiry_days:
            try:
                days = int(expiry_days)
                if days > 0:
                    expiry_date = datetime.now(timezone.utc) + timedelta(days=days)
            except ValueError:
                pass
        
        # Generate QR code with dynamic URL
        qr_url = get_external_url('qr_redirect', uid=uid)
        filename, filepath = qr_generator.generate(
            qr_url,
            uid,
            foreground=foreground,
            background=background,
            logo_path=logo_path
        )
        
        # Create database record
        qr_code = QRCode(
            uid=uid,
            user_id=current_user.id,
            data_type=data_type,
            original_data=data,
            encrypted_data=encrypted_data,
            foreground_color=foreground,
            background_color=background,
            has_logo=has_logo,
            logo_path=logo_path,
            filename=filename,
            file_path=filepath,
            expiry_date=expiry_date
        )
        
        db.session.add(qr_code)
        db.session.commit()
        
        flash('QR code generated successfully!', 'success')
        return redirect(url_for('preview', qr_id=qr_code.id))
    
    return render_template('generate.html')

# ==================== QR REDIRECT/VIEW ====================

@app.route('/qr/<uid>')
def qr_redirect(uid):
    qr_code = QRCode.query.filter_by(uid=uid).first()
    
    if not qr_code:
        return render_template('qr_result.html', 
                             status='invalid', 
                             message='QR Code not found',
                             data=None)
    
    # Log the scan
    log = ScanLog(
        qr_code_id=qr_code.id,
        scanned_data=uid,
        scan_result=qr_code.status,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:512] if request.user_agent.string else None
    )
    db.session.add(log)
    qr_code.increment_scan()
    
    if not qr_code.is_active:
        return render_template('qr_result.html', 
                             status='inactive', 
                             message='This QR code has been deactivated',
                             data=None)
    
    if qr_code.is_expired:
        return render_template('qr_result.html', 
                             status='expired', 
                             message='This QR code has expired',
                             data=None)
    
    # Get the actual data
    data = qr_code.original_data
    if qr_code.encrypted_data:
        try:
            data = encryption.decrypt(qr_code.encrypted_data)
        except:
            data = qr_code.original_data
    
    # If URL, redirect
    if qr_code.data_type == 'url' and validator.validate_url(data):
        return redirect(data)
    
    # Otherwise show data
    return render_template('qr_result.html', 
                         status='valid', 
                         message='QR Code Data',
                         data=data,
                         data_type=qr_code.data_type)

# ==================== QR SCANNING ====================

@app.route('/scan', methods=['GET', 'POST'])
@login_required
def scan():
    if request.method == 'POST':
        results = []
        
        # Handle file upload
        if 'qr_image' in request.files:
            file = request.files['qr_image']
            if file and file.filename and validator.allowed_file(file.filename):
                # Read file data
                file_data = file.read()
                scan_results = qr_scanner.scan_image_data(file_data)
                
                for result in scan_results:
                    qr_data = result['data']
                    processed = process_scanned_qr(qr_data)
                    results.append(processed)
        
        # Handle base64 image from webcam
        elif request.is_json:
            data = request.get_json()
            if 'image' in data:
                import base64
                image_data = data['image'].split(',')[1] if ',' in data['image'] else data['image']
                image_bytes = base64.b64decode(image_data)
                scan_results = qr_scanner.scan_image_data(image_bytes)
                
                for result in scan_results:
                    qr_data = result['data']
                    processed = process_scanned_qr(qr_data)
                    results.append(processed)
                
                return jsonify({'results': results})
        
        if not results:
            flash('No QR codes found in the image.', 'warning')
        else:
            return render_template('scan.html', results=results)
    
    return render_template('scan.html', results=None)

def process_scanned_qr(qr_data):
    """Process scanned QR data and return result dict."""
    result = {
        'raw_data': qr_data,
        'status': 'unknown',
        'message': '',
        'stored_data': None,
        'qr_code': None
    }
    
    # Check if it's a dynamic QR from our system
    if '/qr/' in qr_data:
        uid = qr_data.split('/qr/')[-1].split('?')[0].split('/')[0]
        qr_code = QRCode.query.filter_by(uid=uid).first()
        
        if qr_code:
            result['qr_code'] = qr_code
            
            # Log scan
            log = ScanLog(
                qr_code_id=qr_code.id,
                user_id=current_user.id,
                scanned_data=qr_data,
                scan_result=qr_code.status,
                ip_address=request.remote_addr
            )
            db.session.add(log)
            qr_code.increment_scan()
            
            if not qr_code.is_active:
                result['status'] = 'inactive'
                result['message'] = 'QR code is deactivated'
            elif qr_code.is_expired:
                result['status'] = 'expired'
                result['message'] = 'QR code has expired'
            else:
                result['status'] = 'valid'
                result['message'] = 'Valid QR code'
                data = qr_code.original_data
                if qr_code.encrypted_data:
                    try:
                        data = encryption.decrypt(qr_code.encrypted_data)
                    except:
                        pass
                result['stored_data'] = data
        else:
            result['status'] = 'invalid'
            result['message'] = 'QR code not found in system'
    else:
        result['status'] = 'external'
        result['message'] = 'External QR code'
        result['stored_data'] = qr_data
    
    return result

@app.route('/scan/webcam', methods=['POST'])
@login_required
def scan_webcam():
    """Handle webcam capture scanning."""
    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({'error': 'No image data provided'}), 400
    
    import base64
    try:
        image_data = data['image'].split(',')[1] if ',' in data['image'] else data['image']
        image_bytes = base64.b64decode(image_data)
    except:
        return jsonify({'error': 'Invalid image data'}), 400
    
    scan_results = qr_scanner.scan_image_data(image_bytes)
    
    results = []
    for result in scan_results:
        processed = process_scanned_qr(result['data'])
        results.append(processed)
    
    return jsonify({'results': results})

# ==================== QR HISTORY ====================

@app.route('/history')
@login_required
def history():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Filters
    status_filter = request.args.get('status', '')
    search_query = request.args.get('search', '')
    
    query = current_user.qr_codes
    
    if search_query:
        query = query.filter(QRCode.original_data.ilike(f'%{search_query}%'))
    
    if status_filter == 'active':
        query = query.filter(
            QRCode.is_active == True,
            (QRCode.expiry_date == None) | (QRCode.expiry_date > datetime.now(timezone.utc))
        )
    elif status_filter == 'inactive':
        query = query.filter(QRCode.is_active == False)
    elif status_filter == 'expired':
        query = query.filter(
            QRCode.expiry_date != None,
            QRCode.expiry_date <= datetime.now(timezone.utc)
        )
    
    qr_codes = query.order_by(QRCode.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('history.html', qr_codes=qr_codes, 
                         status_filter=status_filter, search_query=search_query)

@app.route('/preview/<int:qr_id>')
@login_required
def preview(qr_id):
    qr_code = QRCode.query.filter_by(id=qr_id, user_id=current_user.id).first_or_404()
    return render_template('preview.html', qr_code=qr_code)

@app.route('/qr/toggle/<int:qr_id>', methods=['POST'])
@login_required
def toggle_qr(qr_id):
    qr_code = QRCode.query.filter_by(id=qr_id, user_id=current_user.id).first_or_404()
    qr_code.is_active = not qr_code.is_active
    db.session.commit()
    
    status = 'activated' if qr_code.is_active else 'deactivated'
    flash(f'QR code {status} successfully.', 'success')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'is_active': qr_code.is_active})
    
    return redirect(url_for('history'))

@app.route('/qr/delete/<int:qr_id>', methods=['POST'])
@login_required
def delete_qr(qr_id):
    qr_code = QRCode.query.filter_by(id=qr_id, user_id=current_user.id).first_or_404()
    
    # Delete files
    if os.path.exists(qr_code.file_path):
        os.remove(qr_code.file_path)
    if qr_code.logo_path and os.path.exists(qr_code.logo_path):
        os.remove(qr_code.logo_path)
    
    db.session.delete(qr_code)
    db.session.commit()
    
    flash('QR code deleted successfully.', 'success')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    
    return redirect(url_for('history'))

@app.route('/qr/image/<int:qr_id>')
@login_required
def qr_image(qr_id):
    qr_code = QRCode.query.filter_by(id=qr_id, user_id=current_user.id).first_or_404()
    
    if not os.path.exists(qr_code.file_path):
        abort(404)
    
    return send_file(
        qr_code.file_path,
        mimetype='image/png'
    )

@app.route('/qr/download/<int:qr_id>')
@login_required
def download_qr(qr_id):
    qr_code = QRCode.query.filter_by(id=qr_id, user_id=current_user.id).first_or_404()
    
    if not os.path.exists(qr_code.file_path):
        abort(404)
    
    return send_file(
        qr_code.file_path,
        as_attachment=True,
        download_name=f'qrcode_{qr_code.uid[:8]}.png'
    )

@app.route('/qr/view/<int:qr_id>')
@login_required
def view_qr(qr_id):
    qr_code = QRCode.query.filter_by(id=qr_id, user_id=current_user.id).first_or_404()
    return render_template('qr_view.html', qr_code=qr_code)

# ==================== API ENDPOINTS ====================

@app.route('/api/stats')
@login_required
def api_stats():
    stats = current_user.get_stats()
    return jsonify(stats)

@app.route('/api/qr/<int:qr_id>')
@login_required
def api_qr_details(qr_id):
    qr_code = QRCode.query.filter_by(id=qr_id, user_id=current_user.id).first_or_404()
    return jsonify(qr_code.to_dict())

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('base.html', error='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('base.html', error='Internal server error'), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
