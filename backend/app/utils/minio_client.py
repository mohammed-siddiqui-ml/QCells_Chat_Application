"""
MinIO client wrapper for object storage with bucket management and secure file operations.

This module provides:
- Async MinIO client with connection configuration from environment
- Bucket initialization with automatic creation if not exists
- Document upload with metadata storage and content type detection
- Presigned URL generation for secure temporary access
- File type validation and size limit enforcement
- Server-side encryption (SSE) for all uploads
- File download and listing with pagination
"""
import io
import mimetypes
from typing import Any, Dict, List, Optional, BinaryIO
from datetime import timedelta

from minio import Minio
from minio.error import S3Error
from minio.commonconfig import ENABLED
from minio.sse import SseS3

from app.core.config import settings
from app.core.logging import logger


class MinIOClient:
    """
    MinIO client for object storage operations with security features.
    
    Provides methods for bucket management, file upload/download with validation,
    presigned URL generation, and server-side encryption.
    """
    
    # Allowed file types for upload
    ALLOWED_FILE_TYPES = {
        'application/pdf',           # PDF
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # DOCX
        'application/msword',        # DOC
        'text/plain',                # TXT
        'video/mp4',                 # MP4
        'image/png',                 # PNG
        'image/jpeg',                # JPG/JPEG
    }
    
    # Allowed file extensions
    ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt', '.mp4', '.png', '.jpg', '.jpeg'}
    
    # Maximum file size: 100MB
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB in bytes
    
    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        secure: Optional[bool] = None,
        region: Optional[str] = None
    ):
        """
        Initialize MinIO client with connection configuration.
        
        Args:
            endpoint: MinIO server endpoint (default: from settings)
            access_key: Access key for authentication (default: from settings)
            secret_key: Secret key for authentication (default: from settings)
            secure: Use HTTPS for connection (default: from settings)
            region: MinIO region (default: from settings)
        """
        self.endpoint = endpoint or settings.MINIO_ENDPOINT
        self.access_key = access_key or settings.MINIO_ACCESS_KEY
        self.secret_key = secret_key or settings.MINIO_SECRET_KEY
        self.secure = secure if secure is not None else settings.MINIO_SECURE
        self.region = region or settings.MINIO_REGION
        self.bucket_name = settings.MINIO_BUCKET_NAME
        
        # Initialize MinIO client
        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
            region=self.region
        )
        
        logger.info(
            f"MinIO client initialized: endpoint={self.endpoint}, "
            f"secure={self.secure}, bucket={self.bucket_name}"
        )
    
    def ensure_bucket_exists(self, bucket_name: Optional[str] = None) -> bool:
        """
        Ensure bucket exists, create if it doesn't.
        
        This method should be called on application startup to initialize
        the default knowledge-base bucket.
        
        Args:
            bucket_name: Name of the bucket (default: knowledge-base from settings)
            
        Returns:
            True if bucket exists or was created successfully, False otherwise
        """
        bucket_name = bucket_name or self.bucket_name
        
        try:
            # Check if bucket exists
            if self.client.bucket_exists(bucket_name):
                logger.info(f"Bucket '{bucket_name}' already exists")
                return True
            
            # Create bucket
            self.client.make_bucket(bucket_name, location=self.region)
            logger.info(f"Bucket '{bucket_name}' created successfully in region {self.region}")
            
            # Enable versioning for the bucket (optional but recommended)
            # self.client.set_bucket_versioning(bucket_name, ENABLED)
            # logger.info(f"Versioning enabled for bucket '{bucket_name}'")
            
            return True
            
        except S3Error as e:
            logger.error(f"Failed to ensure bucket exists '{bucket_name}': {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error ensuring bucket exists '{bucket_name}': {e}")
            return False
    
    def _validate_file_type(self, filename: str, content_type: Optional[str] = None) -> bool:
        """
        Validate file type based on extension and content type.
        
        Args:
            filename: Name of the file
            content_type: MIME type of the file (optional)
            
        Returns:
            True if file type is allowed, False otherwise
        """
        # Check extension
        extension = filename.lower()[filename.rfind('.'):] if '.' in filename else ''
        if extension not in self.ALLOWED_EXTENSIONS:
            logger.warning(f"File type not allowed: {filename} (extension: {extension})")
            return False
        
        # Check content type if provided
        if content_type and content_type not in self.ALLOWED_FILE_TYPES:
            logger.warning(f"Content type not allowed: {content_type} for file {filename}")
            return False
        
        return True

    def _detect_content_type(self, filename: str) -> str:
        """
        Detect content type from filename.

        Args:
            filename: Name of the file

        Returns:
            MIME type string
        """
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or 'application/octet-stream'

    def _validate_file_size(self, file_size: int) -> bool:
        """
        Validate file size against maximum allowed size.

        Args:
            file_size: Size of the file in bytes

        Returns:
            True if size is within limit, False otherwise
        """
        if file_size > self.MAX_FILE_SIZE:
            logger.warning(
                f"File size {file_size} bytes exceeds maximum allowed size "
                f"{self.MAX_FILE_SIZE} bytes ({self.MAX_FILE_SIZE / 1024 / 1024}MB)"
            )
            return False
        return True

    def upload_document(
        self,
        object_name: str,
        file_data: BinaryIO,
        file_size: int,
        metadata: Optional[Dict[str, str]] = None,
        bucket_name: Optional[str] = None,
        content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upload document to MinIO with metadata and server-side encryption.

        Args:
            object_name: Name of the object in MinIO (path/filename)
            file_data: File data as binary stream
            file_size: Size of the file in bytes
            metadata: Optional metadata dictionary
            bucket_name: Target bucket (default: knowledge-base from settings)
            content_type: MIME type (auto-detected if not provided)

        Returns:
            Dictionary with upload result:
            - success: True/False
            - object_name: Name of the uploaded object
            - etag: ETag of the uploaded object
            - version_id: Version ID if versioning enabled
            - error: Error message if failed
        """
        bucket_name = bucket_name or self.bucket_name

        # Detect content type if not provided
        if content_type is None:
            content_type = self._detect_content_type(object_name)

        # Validate file type
        if not self._validate_file_type(object_name, content_type):
            return {
                "success": False,
                "error": f"File type not allowed. Allowed types: {', '.join(self.ALLOWED_EXTENSIONS)}"
            }

        # Validate file size
        if not self._validate_file_size(file_size):
            return {
                "success": False,
                "error": f"File size exceeds maximum allowed size of {self.MAX_FILE_SIZE / 1024 / 1024}MB"
            }

        try:
            # Ensure bucket exists
            self.ensure_bucket_exists(bucket_name)

            # Configure server-side encryption (SSE-S3)
            sse = SseS3()

            # Upload object with metadata and encryption
            result = self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=file_data,
                length=file_size,
                content_type=content_type,
                metadata=metadata,
                sse=sse
            )

            logger.info(
                f"Document uploaded successfully: {object_name} "
                f"(bucket: {bucket_name}, etag: {result.etag}, size: {file_size} bytes)"
            )

            return {
                "success": True,
                "object_name": result.object_name,
                "etag": result.etag,
                "version_id": result.version_id,
                "bucket_name": bucket_name
            }

        except S3Error as e:
            logger.error(f"Failed to upload document '{object_name}': {e}")
            return {
                "success": False,
                "error": f"S3 error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error uploading document '{object_name}': {e}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}"
            }

    def generate_presigned_url(
        self,
        object_name: str,
        bucket_name: Optional[str] = None,
        expiry: int = 3600
    ) -> Optional[str]:
        """
        Generate presigned URL for secure temporary access to object.

        Args:
            object_name: Name of the object
            bucket_name: Bucket containing the object (default: knowledge-base)
            expiry: URL expiry time in seconds (default: 3600 = 1 hour)

        Returns:
            Presigned URL string or None if failed
        """
        bucket_name = bucket_name or self.bucket_name

        try:
            # Generate presigned GET URL
            url = self.client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=timedelta(seconds=expiry)
            )

            logger.info(
                f"Presigned URL generated for '{object_name}' "
                f"(bucket: {bucket_name}, expiry: {expiry}s)"
            )
            return url

        except S3Error as e:
            logger.error(f"Failed to generate presigned URL for '{object_name}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating presigned URL for '{object_name}': {e}")
            return None

    def download_file(
        self,
        object_name: str,
        bucket_name: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Download file from MinIO.

        Args:
            object_name: Name of the object to download
            bucket_name: Bucket containing the object (default: knowledge-base)

        Returns:
            File data as bytes or None if failed
        """
        bucket_name = bucket_name or self.bucket_name

        try:
            # Get object
            response = self.client.get_object(bucket_name, object_name)

            # Read data
            data = response.read()
            response.close()
            response.release_conn()

            logger.info(
                f"File downloaded successfully: {object_name} "
                f"(bucket: {bucket_name}, size: {len(data)} bytes)"
            )
            return data

        except S3Error as e:
            logger.error(f"Failed to download file '{object_name}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading file '{object_name}': {e}")
            return None

    def list_objects(
        self,
        bucket_name: Optional[str] = None,
        prefix: Optional[str] = None,
        max_objects: int = 100,
        start_after: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List objects in bucket with pagination support.

        Args:
            bucket_name: Bucket to list objects from (default: knowledge-base)
            prefix: Filter objects by prefix (folder path)
            max_objects: Maximum number of objects to return (pagination)
            start_after: Object name to start listing after (for pagination)

        Returns:
            List of object information dictionaries containing:
            - object_name: Name of the object
            - size: Size in bytes
            - last_modified: Last modification timestamp
            - etag: ETag of the object
            - content_type: MIME type
        """
        bucket_name = bucket_name or self.bucket_name

        try:
            objects_list = []
            count = 0

            # List objects
            objects = self.client.list_objects(
                bucket_name=bucket_name,
                prefix=prefix,
                recursive=True,
                start_after=start_after
            )

            for obj in objects:
                # Apply pagination limit
                if count >= max_objects:
                    break

                # Get object metadata
                try:
                    stat = self.client.stat_object(bucket_name, obj.object_name)
                    content_type = stat.content_type
                except:
                    content_type = self._detect_content_type(obj.object_name)

                object_info = {
                    "object_name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "etag": obj.etag,
                    "content_type": content_type,
                    "is_dir": obj.is_dir
                }
                objects_list.append(object_info)
                count += 1

            logger.info(
                f"Listed {len(objects_list)} objects from bucket '{bucket_name}' "
                f"(prefix: {prefix or 'None'}, max: {max_objects})"
            )
            return objects_list

        except S3Error as e:
            logger.error(f"Failed to list objects in bucket '{bucket_name}': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing objects in bucket '{bucket_name}': {e}")
            return []

    def delete_object(
        self,
        object_name: str,
        bucket_name: Optional[str] = None
    ) -> bool:
        """
        Delete an object from MinIO.

        Args:
            object_name: Name of the object to delete
            bucket_name: Bucket containing the object (default: knowledge-base)

        Returns:
            True if deleted successfully, False otherwise
        """
        bucket_name = bucket_name or self.bucket_name

        try:
            self.client.remove_object(bucket_name, object_name)
            logger.info(f"Object deleted successfully: {object_name} (bucket: {bucket_name})")
            return True

        except S3Error as e:
            logger.error(f"Failed to delete object '{object_name}': {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting object '{object_name}': {e}")
            return False

    def object_exists(
        self,
        object_name: str,
        bucket_name: Optional[str] = None
    ) -> bool:
        """
        Check if an object exists in MinIO.

        Args:
            object_name: Name of the object
            bucket_name: Bucket to check (default: knowledge-base)

        Returns:
            True if object exists, False otherwise
        """
        bucket_name = bucket_name or self.bucket_name

        try:
            self.client.stat_object(bucket_name, object_name)
            return True
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return False
            logger.error(f"Error checking object existence '{object_name}': {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking object existence '{object_name}': {e}")
            return False

    def get_object_metadata(
        self,
        object_name: str,
        bucket_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get metadata for an object.

        Args:
            object_name: Name of the object
            bucket_name: Bucket containing the object (default: knowledge-base)

        Returns:
            Dictionary with object metadata or None if failed
        """
        bucket_name = bucket_name or self.bucket_name

        try:
            stat = self.client.stat_object(bucket_name, object_name)

            metadata = {
                "object_name": stat.object_name,
                "size": stat.size,
                "last_modified": stat.last_modified.isoformat() if stat.last_modified else None,
                "etag": stat.etag,
                "content_type": stat.content_type,
                "metadata": stat.metadata,
                "version_id": stat.version_id
            }

            logger.debug(f"Retrieved metadata for object '{object_name}' (bucket: {bucket_name})")
            return metadata

        except S3Error as e:
            logger.error(f"Failed to get metadata for object '{object_name}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting metadata for object '{object_name}': {e}")
            return None


# Create global MinIO client instance
minio_client = MinIOClient()

