import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from PIL import Image
from cryptography.fernet import Fernet
import cv2
from pyzbar import pyzbar
import os
import uuid
import re
from urllib.parse import urlparse
from config import Config
class QRGenerator:
    pass

class QRScanner:
    pass

class DataEncryption:
    pass

class DataValidator:
    pass
class QRGenerator:
    def __init__(self, qr_folder=None):
        self.qr_folder = qr_folder or Config.QR_CODES_FOLDER
        os.makedirs(self.qr_folder, exist_ok=True)
    
    def generate(self, data, uid, foreground='#000000', background='#FFFFFF', logo_path=None):
        """Generate a QR code with customization options."""
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H if logo_path else qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        # Convert hex colors to RGB
        fg_color = self._hex_to_rgb(foreground)
        bg_color = self._hex_to_rgb(background)
        
        # Create image
        img = qr.make_image(
            fill_color=fg_color,
            back_color=bg_color,
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer()
        )
        
        # Convert to PIL Image if needed
        if hasattr(img, 'get_image'):
            img = img.get_image()
        
        # Ensure RGB mode
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Add logo if provided
        if logo_path and os.path.exists(logo_path):
            img = self._add_logo(img, logo_path)
        
        # Save image
        filename = f"qr_{uid}.png"
        filepath = os.path.join(self.qr_folder, filename)
        img.save(filepath, 'PNG')
        
        return filename, filepath
    
    def _hex_to_rgb(self, hex_color):
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def _add_logo(self, qr_img, logo_path):
        """Add a logo to the center of the QR code."""
        try:
            logo = Image.open(logo_path)
            
            # Calculate logo size (max 30% of QR code)
            qr_width, qr_height = qr_img.size
            max_logo_size = int(min(qr_width, qr_height) * 0.3)
            
            # Resize logo maintaining aspect ratio
            logo.thumbnail((max_logo_size, max_logo_size), Image.Resampling.LANCZOS)
            
            # Convert logo to RGBA if necessary
            if logo.mode != 'RGBA':
                logo = logo.convert('RGBA')
            
            # Calculate position to center logo
            logo_width, logo_height = logo.size
            position = (
                (qr_width - logo_width) // 2,
                (qr_height - logo_height) // 2
            )
            
            # Create a white background for logo
            bg_size = (logo_width + 10, logo_height + 10)
            bg_position = (position[0] - 5, position[1] - 5)
            white_bg = Image.new('RGB', bg_size, 'white')
            qr_img.paste(white_bg, bg_position)
            
            # Paste logo
            qr_img.paste(logo, position, logo if logo.mode == 'RGBA' else None)
            
            return qr_img
        except Exception as e:
            print(f"Error adding logo: {e}")
            return qr_img


class QRScanner:
    def __init__(self):
        pass
    
    def scan_image(self, image_path):
        """Scan QR codes from an image file."""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return []
            
            return self._decode_qr(image)
        except Exception as e:
            print(f"Error scanning image: {e}")
            return []
    
    def scan_image_data(self, image_data):
        """Scan QR codes from image bytes."""
        try:
            import numpy as np
            nparr = np.frombuffer(image_data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if image is None:
                return []
            
            return self._decode_qr(image)
        except Exception as e:
            print(f"Error scanning image data: {e}")
            return []
    
    def _decode_qr(self, image):
        """Decode QR codes from an OpenCV image."""
        results = []
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Try different preprocessing techniques
        images_to_scan = [
            gray,
            cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
            cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        ]
        
        decoded_set = set()
        
        for img in images_to_scan:
            decoded = pyzbar.decode(img)
            for obj in decoded:
                data = obj.data.decode('utf-8')
                if data not in decoded_set:
                    decoded_set.add(data)
                    results.append({
                        'data': data,
                        'type': obj.type,
                        'rect': {
                            'x': obj.rect.left,
                            'y': obj.rect.top,
                            'width': obj.rect.width,
                            'height': obj.rect.height
                        }
                    })
        
        return results


class DataEncryption:
    def __init__(self, key=None):
        self.key = key or Config.ENCRYPTION_KEY.encode()
        self.fernet = Fernet(self.key)
    
    def encrypt(self, data):
        """Encrypt data using Fernet."""
        if isinstance(data, str):
            data = data.encode()
        return self.fernet.encrypt(data).decode()
    
    def decrypt(self, encrypted_data):
        """Decrypt data using Fernet."""
        if isinstance(encrypted_data, str):
            encrypted_data = encrypted_data.encode()
        return self.fernet.decrypt(encrypted_data).decode()


class DataValidator:
    @staticmethod
    def validate_url(url):
        """Validate URL format."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    @staticmethod
    def validate_email(email):
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def validate_hex_color(color):
        """Validate hex color format."""
        pattern = r'^#[0-9A-Fa-f]{6}$'
        return re.match(pattern, color) is not None
    
    @staticmethod
    def sanitize_filename(filename):
        """Sanitize filename for safe storage."""
        # Remove path separators and null bytes
        filename = os.path.basename(filename)
        filename = filename.replace('\x00', '')
        # Keep only safe characters
        safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-')
        return ''.join(c if c in safe_chars else '_' for c in filename)
    
    @staticmethod
    def allowed_file(filename, allowed_extensions=None):
        """Check if file extension is allowed."""
        if allowed_extensions is None:
            allowed_extensions = Config.ALLOWED_EXTENSIONS
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions
