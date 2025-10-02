"""
Backup API Endpoints for QuizClash
Provides REST API endpoints for database backup and restore operations
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse
from typing import Dict, List, Any, Optional
import os
import tempfile
from datetime import datetime
from .database_backup import DatabaseBackupManager
from .auth import get_current_user, get_admin_user
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/backup", tags=["backup"])
backup_router = router  # Keep backup_router for internal use

# Initialize backup manager
backup_manager = DatabaseBackupManager()

@backup_router.post("/create-full")
async def create_full_backup(
    backup_data: Optional[Dict[str, Any]] = None,
    current_user = Depends(get_admin_user)
):
    """Create a full database backup"""
    try:
        # Extract backup name from data
        backup_name = None
        if backup_data and isinstance(backup_data, dict):
            backup_name = backup_data.get("backup_name")
        
        # Create backup
        result = backup_manager.create_full_backup(backup_name)
        
        if result["success"]:
            logger.info(f"Full backup created by user {current_user.username}: {result['backup_path']}")
            return {
                "status": "success",
                "message": result["message"],
                "backup_info": {
                    "backup_name": result["metadata"]["backup_name"],
                    "timestamp": result["metadata"]["timestamp"],
                    "backup_path": result["backup_path"],
                    "tables_backed_up": result["metadata"]["tables_backed_up"],
                    "record_counts": result["metadata"]["record_counts"]
                }
            }
        else:
            raise HTTPException(status_code=500, detail=result["message"])
            
    except Exception as e:
        logger.error(f"Full backup creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Backup creation failed: {str(e)}")

@backup_router.post("/create-incremental")
async def create_incremental_backup(
    backup_data: Dict[str, Any],
    current_user = Depends(get_admin_user)
):
    """Create an incremental backup"""
    try:
        base_backup_path = backup_data.get("base_backup_path")
        backup_name = backup_data.get("backup_name")
        
        if not base_backup_path:
            raise HTTPException(status_code=400, detail="Base backup path is required")
        
        # Create incremental backup
        result = backup_manager.create_incremental_backup(base_backup_path, backup_name)
        
        if result["success"]:
            logger.info(f"Incremental backup created by user {current_user.username}: {result['backup_path']}")
            return {
                "status": "success",
                "message": result["message"],
                "backup_info": {
                    "backup_name": result["metadata"]["backup_name"],
                    "timestamp": result["metadata"]["timestamp"],
                    "backup_path": result["backup_path"],
                    "base_backup": result["metadata"]["base_backup"],
                    "changes": result["metadata"]["changes"]
                }
            }
        else:
            raise HTTPException(status_code=500, detail=result["message"])
            
    except Exception as e:
        logger.error(f"Incremental backup creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Incremental backup creation failed: {str(e)}")

@backup_router.get("/list")
async def list_backups(current_user = Depends(get_admin_user)):
    """List all available backups"""
    try:
        backups_result = backup_manager.list_backups()
        
        if not backups_result.get("success"):
            raise HTTPException(status_code=500, detail="Failed to retrieve backups")
        
        # Format backup information for API response
        backup_list = []
        for backup in backups_result.get("backups", []):
            backup_info = {
                "file_name": backup["file_name"],
                "file_path": backup["file_path"],
                "file_size": backup["file_size"],
                "created_date": backup["created_date"].isoformat(),
                "backup_name": backup["metadata"]["backup_name"],
                "backup_type": backup["metadata"]["backup_type"],
                "timestamp": backup["metadata"]["timestamp"],
                "tables_backed_up": backup["metadata"].get("tables_backed_up", []),
                "record_counts": backup["metadata"].get("record_counts", {})
            }
            backup_list.append(backup_info)
        
        return {
            "status": "success",
            "backups": backup_list,
            "total_backups": len(backup_list)
        }
        
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list backups: {str(e)}")

@backup_router.get("/download/{backup_name}")
async def download_backup(
    backup_name: str,
    current_user = Depends(get_admin_user)
):
    """Download a backup file"""
    try:
        # Find backup file
        backup_path = backup_manager.backup_dir / f"{backup_name}.zip"
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup file not found")
        
        logger.info(f"Backup download requested by user {current_user.username}: {backup_name}")
        
        return FileResponse(
            path=str(backup_path),
            filename=f"{backup_name}.zip",
            media_type="application/zip"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download backup: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download backup: {str(e)}")

@backup_router.post("/restore")
async def restore_backup(
    backup_data: Dict[str, Any],
    current_user = Depends(get_admin_user)
):
    """Restore database from backup"""
    try:
        backup_path = backup_data.get("backup_path")
        restore_options = backup_data.get("restore_options")
        
        # Perform restore
        result = backup_manager.restore_from_backup(backup_path, restore_options)
        
        if result["success"]:
            logger.info(f"Database restored by user {current_user.username} from: {backup_path}")
            return {
                "status": "success",
                "message": result["message"],
                "restore_info": {
                    "restored_tables": result.get("restored_tables", []),
                    "restored_records": result.get("restored_records", {})
                }
            }
        else:
            raise HTTPException(status_code=500, detail=result["message"])
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database restore failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database restore failed: {str(e)}")

@backup_router.post("/upload-restore")
async def upload_and_restore_backup(
    backup_file: UploadFile = File(...),
    current_user = Depends(get_admin_user)
):
    """Upload and restore from backup file"""
    try:
        # Validate file type
        if not backup_file.filename.endswith('.zip'):
            raise HTTPException(status_code=400, detail="Only ZIP backup files are supported")
        
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
            content = await backup_file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        try:
            # Restore from uploaded file
            result = backup_manager.restore_from_backup(temp_file_path)
            
            if result["success"]:
                logger.info(f"Database restored by user {current_user.username} from uploaded file: {backup_file.filename}")
                return {
                    "status": "success",
                    "message": result["message"],
                    "restore_info": {
                        "restored_tables": result.get("restored_tables", []),
                        "restored_records": result.get("restored_records", {})
                    }
                }
            else:
                raise HTTPException(status_code=500, detail=result["message"])
                
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_file_path)
            except:
                pass
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload and restore failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload and restore failed: {str(e)}")

@backup_router.delete("/delete/{backup_name}")
async def delete_backup(
    backup_name: str,
    current_user = Depends(get_admin_user)
):
    """Delete a backup file"""
    try:
        # Find and delete backup
        backup_path = backup_manager.backup_dir / f"{backup_name}.zip"
        result = backup_manager.delete_backup(str(backup_path))
        
        if result["success"]:
            logger.info(f"Backup deleted by user {current_user.username}: {backup_name}")
            return {
                "status": "success",
                "message": result["message"]
            }
        else:
            raise HTTPException(status_code=404, detail=result["message"])
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete backup: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete backup: {str(e)}")

@backup_router.get("/status")
async def get_backup_status(current_user = Depends(get_admin_user)):
    """Get backup system status and statistics"""
    try:
        
        backups_result = backup_manager.list_backups()
        
        if not backups_result.get("success"):
            raise HTTPException(status_code=500, detail="Failed to retrieve backup status")
        
        backups = backups_result.get("backups", [])
        
        # Calculate statistics
        total_backups = len(backups)
        total_size = sum(backup["file_size"] for backup in backups)
        
        full_backups = [b for b in backups if b["metadata"]["backup_type"] == "full"]
        incremental_backups = [b for b in backups if b["metadata"]["backup_type"] == "incremental"]
        
        latest_backup = backups[0] if backups else None
        
        return {
            "status": "success",
            "total_backups": total_backups,
            "full_backups": len(full_backups),
            "incremental_backups": len(incremental_backups),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "last_backup_date": latest_backup["created_date"].isoformat() if latest_backup else "Never",
            "backup_directory": str(backup_manager.backup_dir)
        }
        
    except Exception as e:
        logger.error(f"Failed to get backup status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get backup status: {str(e)}")
