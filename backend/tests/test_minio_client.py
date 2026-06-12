"""
Test suite for MinIO client with unit and integration tests.

Tests cover:
- Configuration and initialization
- Bucket operations
- File upload/download with validation
- Presigned URL generation
- Object listing and metadata
- Error handling
"""
import io
import pytest
from unittest.mock import Mock, MagicMock, patch, ANY
from datetime import datetime
from minio.error import S3Error
from minio.datatypes import Object

from app.utils.minio_client import MinIOClient


@pytest.fixture
def mock_minio_client():
    """Mock MinIO client for unit tests"""
    with patch('app.utils.minio_client.Minio') as mock:
        yield mock


@pytest.fixture
def minio_client_instance(mock_minio_client):
    """Create MinIOClient instance with mocked Minio"""
    client = MinIOClient(
        endpoint="localhost:9000",
        access_key="test_access",
        secret_key="test_secret",
        secure=False,
        region="us-east-1"
    )
    return client


class TestMinIOClientInitialization:
    """Test MinIO client initialization and configuration"""
    
    def test_init_with_default_settings(self, mock_minio_client):
        """TC-A1: MinIO client initializes with default configuration"""
        client = MinIOClient()
        
        assert client is not None
        assert client.client is not None
        mock_minio_client.assert_called_once()
    
    def test_init_with_custom_config(self, mock_minio_client):
        """TC-A2: MinIO client initializes with custom configuration"""
        client = MinIOClient(
            endpoint="custom:9000",
            access_key="custom_key",
            secret_key="custom_secret",
            secure=True,
            region="eu-west-1"
        )
        
        assert client.endpoint == "custom:9000"
        assert client.access_key == "custom_key"
        assert client.secret_key == "custom_secret"
        assert client.secure == True
        assert client.region == "eu-west-1"


class TestBucketOperations:
    """Test bucket creation and management"""
    
    def test_ensure_bucket_exists_creates_bucket(self, minio_client_instance):
        """TC-A3: Bucket creation when bucket doesn't exist"""
        minio_client_instance.client.bucket_exists.return_value = False
        minio_client_instance.client.make_bucket.return_value = None
        
        result = minio_client_instance.ensure_bucket_exists("test-bucket")
        
        assert result == True
        minio_client_instance.client.bucket_exists.assert_called_once_with("test-bucket")
        minio_client_instance.client.make_bucket.assert_called_once()
    
    def test_ensure_bucket_exists_already_exists(self, minio_client_instance):
        """TC-A4: Bucket already exists (idempotent operation)"""
        minio_client_instance.client.bucket_exists.return_value = True
        
        result = minio_client_instance.ensure_bucket_exists("test-bucket")
        
        assert result == True
        minio_client_instance.client.bucket_exists.assert_called_once_with("test-bucket")
        minio_client_instance.client.make_bucket.assert_not_called()
    
    def test_ensure_bucket_exists_handles_s3_error(self, minio_client_instance):
        """TC-A6: Invalid credentials or S3 error handling"""
        minio_client_instance.client.bucket_exists.side_effect = S3Error(
            code="AccessDenied",
            message="Access Denied",
            resource="test-bucket",
            request_id="req123",
            host_id="host123",
            response=Mock()
        )
        
        result = minio_client_instance.ensure_bucket_exists("test-bucket")
        
        assert result == False


class TestFileValidation:
    """Test file type and size validation"""
    
    def test_validate_file_type_valid_pdf(self, minio_client_instance):
        """Validate allowed PDF file"""
        result = minio_client_instance._validate_file_type("test.pdf", "application/pdf")
        assert result == True
    
    def test_validate_file_type_valid_docx(self, minio_client_instance):
        """Validate allowed DOCX file"""
        result = minio_client_instance._validate_file_type(
            "test.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert result == True
    
    def test_validate_file_type_invalid_exe(self, minio_client_instance):
        """TC-B8: Reject file with invalid extension (.exe)"""
        result = minio_client_instance._validate_file_type("malware.exe", "application/x-msdownload")
        assert result == False

    def test_validate_file_size_within_limit(self, minio_client_instance):
        """Validate file size within 100MB limit"""
        result = minio_client_instance._validate_file_size(50 * 1024 * 1024)  # 50MB
        assert result == True

    def test_validate_file_size_exceeds_limit(self, minio_client_instance):
        """TC-B7: Reject file exceeding 100MB limit"""
        result = minio_client_instance._validate_file_size(101 * 1024 * 1024)  # 101MB
        assert result == False

    def test_detect_content_type_pdf(self, minio_client_instance):
        """Detect content type for PDF file"""
        content_type = minio_client_instance._detect_content_type("test.pdf")
        assert content_type == "application/pdf"

    def test_detect_content_type_unknown(self, minio_client_instance):
        """Detect content type for unknown file"""
        content_type = minio_client_instance._detect_content_type("test.unknown")
        assert content_type == "application/octet-stream"


class TestFileUpload:
    """Test file upload operations with validation and encryption"""

    def test_upload_valid_pdf_with_metadata(self, minio_client_instance):
        """TC-B1: Upload valid PDF file with metadata"""
        # Mock bucket exists check
        minio_client_instance.client.bucket_exists.return_value = True

        # Mock upload result
        mock_result = Mock()
        mock_result.object_name = "test.pdf"
        mock_result.etag = "abc123"
        mock_result.version_id = "v1"
        minio_client_instance.client.put_object.return_value = mock_result

        # Create test file data
        file_data = io.BytesIO(b"%PDF-1.4 test content")
        file_size = 1024
        metadata = {"author": "Test User", "category": "manual"}

        result = minio_client_instance.upload_document(
            object_name="test.pdf",
            file_data=file_data,
            file_size=file_size,
            metadata=metadata
        )

        assert result["success"] == True
        assert result["object_name"] == "test.pdf"
        assert result["etag"] == "abc123"
        assert "version_id" in result

        # Verify put_object was called with correct parameters
        minio_client_instance.client.put_object.assert_called_once()
        call_args = minio_client_instance.client.put_object.call_args
        assert call_args.kwargs["metadata"] == metadata
        assert call_args.kwargs["content_type"] == "application/pdf"

    def test_upload_file_exceeding_size_limit(self, minio_client_instance):
        """TC-B7: Attempt to upload 101MB file"""
        file_data = io.BytesIO(b"x" * 1024)
        file_size = 101 * 1024 * 1024  # 101MB

        result = minio_client_instance.upload_document(
            object_name="large.pdf",
            file_data=file_data,
            file_size=file_size
        )

        assert result["success"] == False
        assert "100" in result["error"] or "size" in result["error"].lower()

    def test_upload_invalid_file_type(self, minio_client_instance):
        """TC-B8: Attempt to upload .exe file"""
        file_data = io.BytesIO(b"MZ executable")
        file_size = 1024

        result = minio_client_instance.upload_document(
            object_name="malware.exe",
            file_data=file_data,
            file_size=file_size
        )

        assert result["success"] == False
        assert "not allowed" in result["error"].lower() or "type" in result["error"].lower()

    def test_upload_handles_s3_error(self, minio_client_instance):
        """Upload handles S3 errors gracefully"""
        minio_client_instance.client.bucket_exists.return_value = True
        minio_client_instance.client.put_object.side_effect = S3Error(
            code="InternalError",
            message="Internal Server Error",
            resource="test.pdf",
            request_id="req123",
            host_id="host123",
            response=Mock()
        )

        file_data = io.BytesIO(b"%PDF-1.4 test")
        result = minio_client_instance.upload_document(
            object_name="test.pdf",
            file_data=file_data,
            file_size=1024
        )

        assert result["success"] == False
        assert "error" in result


class TestFileDownload:
    """Test file download operations"""

    def test_download_existing_file(self, minio_client_instance):
        """TC-C1: Download existing file successfully"""
        # Mock response
        mock_response = Mock()
        mock_response.read.return_value = b"%PDF-1.4 test content"
        minio_client_instance.client.get_object.return_value = mock_response

        data = minio_client_instance.download_file("test.pdf")

        assert data == b"%PDF-1.4 test content"
        minio_client_instance.client.get_object.assert_called_once()
        mock_response.close.assert_called_once()
        mock_response.release_conn.assert_called_once()

    def test_download_non_existent_file(self, minio_client_instance):
        """TC-C2: Download non-existent file (error handling)"""
        minio_client_instance.client.get_object.side_effect = S3Error(
            code="NoSuchKey",
            message="The specified key does not exist",
            resource="missing.pdf",
            request_id="req123",
            host_id="host123",
            response=Mock()
        )

        data = minio_client_instance.download_file("missing.pdf")

        assert data is None


class TestPresignedURLs:
    """Test presigned URL generation"""

    def test_generate_presigned_url_default_expiry(self, minio_client_instance):
        """TC-D1: Generate presigned URL with default expiry (3600s)"""
        expected_url = "http://localhost:9000/test-bucket/test.pdf?X-Amz-Expires=3600&..."
        minio_client_instance.client.presigned_get_object.return_value = expected_url

        url = minio_client_instance.generate_presigned_url("test.pdf")

        assert url == expected_url
        minio_client_instance.client.presigned_get_object.assert_called_once()
        call_args = minio_client_instance.client.presigned_get_object.call_args
        assert call_args.kwargs["expires"].total_seconds() == 3600

    def test_generate_presigned_url_custom_expiry(self, minio_client_instance):
        """TC-D2: Generate presigned URL with custom expiry"""
        expected_url = "http://localhost:9000/test-bucket/test.pdf?X-Amz-Expires=7200&..."
        minio_client_instance.client.presigned_get_object.return_value = expected_url

        url = minio_client_instance.generate_presigned_url("test.pdf", expiry=7200)

        assert url == expected_url
        call_args = minio_client_instance.client.presigned_get_object.call_args
        assert call_args.kwargs["expires"].total_seconds() == 7200

    def test_generate_presigned_url_handles_error(self, minio_client_instance):
        """TC-D5: Generate URL for non-existent object (error handling)"""
        minio_client_instance.client.presigned_get_object.side_effect = S3Error(
            code="NoSuchKey",
            message="Object not found",
            resource="missing.pdf",
            request_id="req123",
            host_id="host123",
            response=Mock()
        )

        url = minio_client_instance.generate_presigned_url("missing.pdf")

        assert url is None


class TestObjectListing:
    """Test object listing and pagination"""

    def test_list_all_objects(self, minio_client_instance):
        """TC-E1: List all objects in bucket"""
        # Create mock objects
        mock_objects = []
        for i in range(5):
            obj = Mock(spec=Object)
            obj.object_name = f"test{i+1}.pdf"
            obj.size = 1024 * (i + 1)
            obj.last_modified = datetime(2024, 1, i+1)
            obj.etag = f"etag{i+1}"
            obj.is_dir = False
            mock_objects.append(obj)

        minio_client_instance.client.list_objects.return_value = iter(mock_objects)

        # Mock stat_object for content type
        mock_stat = Mock()
        mock_stat.content_type = "application/pdf"
        minio_client_instance.client.stat_object.return_value = mock_stat

        objects = minio_client_instance.list_objects()

        assert len(objects) == 5
        assert objects[0]["object_name"] == "test1.pdf"
        assert objects[0]["size"] == 1024
        assert "last_modified" in objects[0]
        assert "content_type" in objects[0]

    def test_list_objects_with_prefix(self, minio_client_instance):
        """TC-E2: List objects with prefix filter"""
        mock_obj = Mock(spec=Object)
        mock_obj.object_name = "documents/test.pdf"
        mock_obj.size = 2048
        mock_obj.last_modified = datetime(2024, 1, 1)
        mock_obj.etag = "etag1"
        mock_obj.is_dir = False

        minio_client_instance.client.list_objects.return_value = iter([mock_obj])

        mock_stat = Mock()
        mock_stat.content_type = "application/pdf"
        minio_client_instance.client.stat_object.return_value = mock_stat

        objects = minio_client_instance.list_objects(prefix="documents/")

        assert len(objects) == 1
        assert objects[0]["object_name"] == "documents/test.pdf"

        # Verify prefix was passed
        call_args = minio_client_instance.client.list_objects.call_args
        assert call_args.kwargs["prefix"] == "documents/"

    def test_list_objects_with_pagination(self, minio_client_instance):
        """TC-E3: List objects with pagination (max_objects)"""
        # Create 10 mock objects but limit to 5
        mock_objects = []
        for i in range(10):
            obj = Mock(spec=Object)
            obj.object_name = f"test{i+1}.pdf"
            obj.size = 1024
            obj.last_modified = datetime(2024, 1, 1)
            obj.etag = f"etag{i+1}"
            obj.is_dir = False
            mock_objects.append(obj)

        minio_client_instance.client.list_objects.return_value = iter(mock_objects)

        mock_stat = Mock()
        mock_stat.content_type = "application/pdf"
        minio_client_instance.client.stat_object.return_value = mock_stat

        objects = minio_client_instance.list_objects(max_objects=5)

        # Should return exactly 5 objects
        assert len(objects) == 5

    def test_list_empty_bucket(self, minio_client_instance):
        """TC-E4: List empty bucket"""
        minio_client_instance.client.list_objects.return_value = iter([])

        objects = minio_client_instance.list_objects()

        assert len(objects) == 0
        assert objects == []


class TestUtilityOperations:
    """Test object existence, metadata, and deletion"""

    def test_object_exists_true(self, minio_client_instance):
        """TC-F1: Check existence of existing object"""
        mock_stat = Mock()
        minio_client_instance.client.stat_object.return_value = mock_stat

        exists = minio_client_instance.object_exists("test.pdf")

        assert exists == True
        minio_client_instance.client.stat_object.assert_called_once()

    def test_object_exists_false(self, minio_client_instance):
        """TC-F2: Check existence of non-existent object"""
        minio_client_instance.client.stat_object.side_effect = S3Error(
            code="NoSuchKey",
            message="Object not found",
            resource="missing.pdf",
            request_id="req123",
            host_id="host123",
            response=Mock()
        )

        exists = minio_client_instance.object_exists("missing.pdf")

        assert exists == False

    def test_get_object_metadata_success(self, minio_client_instance):
        """TC-F3: Get metadata of existing object"""
        mock_stat = Mock()
        mock_stat.object_name = "test.pdf"
        mock_stat.size = 2048
        mock_stat.last_modified = datetime(2024, 1, 1)
        mock_stat.etag = "abc123"
        mock_stat.content_type = "application/pdf"
        mock_stat.metadata = {"author": "Test User"}
        mock_stat.version_id = "v1"
        minio_client_instance.client.stat_object.return_value = mock_stat

        metadata = minio_client_instance.get_object_metadata("test.pdf")

        assert metadata is not None
        assert metadata["object_name"] == "test.pdf"
        assert metadata["size"] == 2048
        assert metadata["content_type"] == "application/pdf"
        assert metadata["metadata"]["author"] == "Test User"

    def test_get_object_metadata_not_found(self, minio_client_instance):
        """TC-F4: Get metadata of non-existent object"""
        minio_client_instance.client.stat_object.side_effect = S3Error(
            code="NoSuchKey",
            message="Object not found",
            resource="missing.pdf",
            request_id="req123",
            host_id="host123",
            response=Mock()
        )

        metadata = minio_client_instance.get_object_metadata("missing.pdf")

        assert metadata is None

    def test_delete_object_success(self, minio_client_instance):
        """TC-F5: Delete existing object"""
        minio_client_instance.client.remove_object.return_value = None

        result = minio_client_instance.delete_object("test.pdf")

        assert result == True
        minio_client_instance.client.remove_object.assert_called_once()

    def test_delete_object_handles_error(self, minio_client_instance):
        """TC-F6: Delete handles errors gracefully"""
        minio_client_instance.client.remove_object.side_effect = S3Error(
            code="InternalError",
            message="Internal error",
            resource="test.pdf",
            request_id="req123",
            host_id="host123",
            response=Mock()
        )

        result = minio_client_instance.delete_object("test.pdf")

        assert result == False
