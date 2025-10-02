"""
Database Backup and Restore System for QuizClash
Provides comprehensive backup and restore functionality for SQLite database
"""

import sqlite3
import json
import os
import shutil
import zipfile
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import hashlib
import logging

class DatabaseBackupManager:
    """Manages database backup and restore operations"""
    
    def __init__(self, db_path: str = "quizclash.db"):
        self.db_path = db_path
        self.backup_dir = Path("backups")
        self.backup_dir.mkdir(exist_ok=True)
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def create_full_backup(self, backup_name: Optional[str] = None) -> Dict[str, Any]:
        """Create a complete database backup with metadata"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            if not backup_name:
                backup_name = f"quizclash_backup_{timestamp}"
            
            backup_path = self.backup_dir / f"{backup_name}.zip"
            
            # Create backup metadata
            metadata = {
                "backup_name": backup_name,
                "timestamp": timestamp,
                "database_path": self.db_path,
                "backup_type": "full",
                "version": "1.0",
                "tables_backed_up": [],
                "record_counts": {},
                "file_hash": None
            }
            
            # Create temporary directory for backup files
            temp_dir = self.backup_dir / f"temp_{timestamp}"
            temp_dir.mkdir(exist_ok=True)
            
            try:
                # Copy database file
                db_backup_path = temp_dir / "database.db"
                shutil.copy2(self.db_path, db_backup_path)
                
                # Export data as JSON for additional safety
                json_data = self._export_database_to_json()
                json_backup_path = temp_dir / "data_export.json"
                with open(json_backup_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, default=str)
                
                # Update metadata
                metadata["tables_backed_up"] = list(json_data.keys())
                metadata["record_counts"] = {
                    table: len(records) for table, records in json_data.items()
                }
                
                # Create ZIP archive first without metadata
                with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in temp_dir.rglob('*'):
                        if file_path.is_file():
                            arcname = file_path.relative_to(temp_dir)
                            zipf.write(file_path, arcname)
                
                # Calculate file hash before adding metadata
                file_hash = self._calculate_file_hash(backup_path)
                metadata["file_hash"] = file_hash
                
                # Add metadata to backup (this will change the hash, but we store the pre-metadata hash)
                with zipfile.ZipFile(backup_path, 'a') as zipf:
                    zipf.writestr("metadata.json", json.dumps(metadata, indent=2))
                
                self.logger.info(f"Full backup created: {backup_path}")
                
                return {
                    "success": True,
                    "backup_path": str(backup_path),
                    "metadata": metadata,
                    "message": f"Full backup created successfully: {backup_name}"
                }
                
            finally:
                # Clean up temporary directory
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except Exception as e:
            self.logger.error(f"Backup creation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Backup creation failed: {e}"
            }
    
    def create_incremental_backup(self, base_backup_path: str, backup_name: Optional[str] = None) -> Dict[str, Any]:
        """Create an incremental backup based on changes since base backup"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            if not backup_name:
                backup_name = f"quizclash_incremental_{timestamp}"
            
            # Load base backup metadata
            base_metadata = self._load_backup_metadata(base_backup_path)
            if not base_metadata:
                return {
                    "success": False,
                    "error": "Could not load base backup metadata",
                    "message": "Invalid base backup file"
                }
            
            # Get current data
            current_data = self._export_database_to_json()
            
            # Calculate changes
            changes = self._calculate_data_changes(base_metadata["record_counts"], current_data)
            
            backup_path = self.backup_dir / f"{backup_name}.zip"
            
            # Create incremental backup metadata
            metadata = {
                "backup_name": backup_name,
                "timestamp": timestamp,
                "database_path": self.db_path,
                "backup_type": "incremental",
                "base_backup": base_backup_path,
                "version": "1.0",
                "changes": changes,
                "file_hash": None
            }
            
            # Create temporary directory
            temp_dir = self.backup_dir / f"temp_inc_{timestamp}"
            temp_dir.mkdir(exist_ok=True)
            
            try:
                # Save only changed data
                changes_path = temp_dir / "changes.json"
                with open(changes_path, 'w', encoding='utf-8') as f:
                    json.dump(changes, f, indent=2, default=str)
                
                # Save metadata
                metadata_path = temp_dir / "metadata.json"
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2)
                
                # Create ZIP archive
                with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in temp_dir.rglob('*'):
                        if file_path.is_file():
                            arcname = file_path.relative_to(temp_dir)
                            zipf.write(file_path, arcname)
                
                # Calculate file hash
                file_hash = self._calculate_file_hash(backup_path)
                metadata["file_hash"] = file_hash
                
                self.logger.info(f"Incremental backup created: {backup_path}")
                
                return {
                    "success": True,
                    "backup_path": str(backup_path),
                    "metadata": metadata,
                    "changes_summary": changes,
                    "message": f"Incremental backup created successfully: {backup_name}"
                }
                
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except Exception as e:
            self.logger.error(f"Incremental backup creation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Incremental backup creation failed: {e}"
            }
    
    def restore_from_backup(self, backup_path: str, restore_options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Restore database from backup file"""
        try:
            if not os.path.exists(backup_path):
                return {
                    "success": False,
                    "error": "Backup file not found",
                    "message": f"Backup file does not exist: {backup_path}"
                }
            
            # Load backup metadata
            metadata = self._load_backup_metadata(backup_path)
            if not metadata:
                return {
                    "success": False,
                    "error": "Invalid backup file",
                    "message": "Could not read backup metadata"
                }
            
            # Verify backup integrity
            if not self._verify_backup_integrity(backup_path, metadata):
                return {
                    "success": False,
                    "error": "Backup integrity check failed",
                    "message": "Backup file appears to be corrupted"
                }
            
            # Create backup of current database
            current_backup = self.create_full_backup(f"pre_restore_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}")
            
            try:
                if metadata["backup_type"] == "full":
                    result = self._restore_full_backup(backup_path, metadata, restore_options)
                elif metadata["backup_type"] == "incremental":
                    result = self._restore_incremental_backup(backup_path, metadata, restore_options)
                else:
                    return {
                        "success": False,
                        "error": "Unknown backup type",
                        "message": f"Unsupported backup type: {metadata['backup_type']}"
                    }
                
                if result["success"]:
                    self.logger.info(f"Database restored from: {backup_path}")
                
                return result
                
            except Exception as restore_error:
                # Attempt to restore from pre-restore backup
                self.logger.error(f"Restore failed, attempting rollback: {restore_error}")
                if current_backup["success"]:
                    rollback_result = self._restore_full_backup(
                        current_backup["backup_path"], 
                        current_backup["metadata"]
                    )
                    if rollback_result["success"]:
                        return {
                            "success": False,
                            "error": str(restore_error),
                            "message": f"Restore failed, database rolled back to previous state: {restore_error}"
                        }
                
                return {
                    "success": False,
                    "error": str(restore_error),
                    "message": f"Restore failed and rollback unsuccessful: {restore_error}"
                }
                
        except Exception as e:
            self.logger.error(f"Restore operation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Restore operation failed: {e}"
            }
    
    def list_backups(self) -> Dict[str, Any]:
        """List all available backups with metadata"""
        backups = []
        
        for backup_file in self.backup_dir.glob("*.zip"):
            try:
                metadata = self._load_backup_metadata(str(backup_file))
                if metadata:
                    file_stats = backup_file.stat()
                    backup_info = {
                        "file_path": str(backup_file),
                        "file_name": backup_file.name,
                        "file_size": file_stats.st_size,
                        "created_date": datetime.datetime.fromtimestamp(file_stats.st_ctime),
                        "created_at": datetime.datetime.fromtimestamp(file_stats.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                        "backup_name": metadata.get("backup_name", backup_file.stem),
                        "backup_type": metadata.get("backup_type", "unknown"),
                        "metadata": metadata
                    }
                    backups.append(backup_info)
            except Exception as e:
                self.logger.warning(f"Could not read backup metadata for {backup_file}: {e}")
        
        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x["created_date"], reverse=True)
        
        return {
            "success": True,
            "backups": backups,
            "total_count": len(backups),
            "message": f"Found {len(backups)} backup(s)"
        }
    
    def delete_backup(self, backup_path: str) -> Dict[str, Any]:
        """Delete a backup file"""
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
                self.logger.info(f"Backup deleted: {backup_path}")
                return {
                    "success": True,
                    "message": f"Backup deleted successfully: {os.path.basename(backup_path)}"
                }
            else:
                return {
                    "success": False,
                    "error": "File not found",
                    "message": f"Backup file not found: {backup_path}"
                }
        except Exception as e:
            self.logger.error(f"Failed to delete backup: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to delete backup: {e}"
            }
    
    def _export_database_to_json(self) -> Dict[str, List[Dict]]:
        """Export entire database to JSON format"""
        data = {}
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                data[table] = [dict(row) for row in rows]
        
        return data
    
    def _calculate_data_changes(self, base_counts: Dict[str, int], current_data: Dict[str, List]) -> Dict[str, Any]:
        """Calculate detailed changes between base backup and current data"""
        changes = {
            "new_tables": [],
            "deleted_tables": [],
            "modified_tables": {},
            "table_data": {}
        }
        
        base_tables = set(base_counts.keys())
        current_tables = set(current_data.keys())
        
        changes["new_tables"] = list(current_tables - base_tables)
        changes["deleted_tables"] = list(base_tables - current_tables)
        
        # For new tables, include all data
        for table in changes["new_tables"]:
            changes["table_data"][table] = {
                "action": "create",
                "data": current_data[table]
            }
        
        # For existing tables, detect changes
        for table in current_tables.intersection(base_tables):
            base_count = base_counts[table]
            current_count = len(current_data[table])
            
            if base_count != current_count:
                changes["modified_tables"][table] = {
                    "base_count": base_count,
                    "current_count": current_count,
                    "change": current_count - base_count
                }
                
                # Store the current data for modified tables
                # In a real implementation, we'd calculate actual diffs
                changes["table_data"][table] = {
                    "action": "update",
                    "data": current_data[table]
                }
        
        return changes
    
    def _load_backup_metadata(self, backup_path: str) -> Optional[Dict[str, Any]]:
        """Load metadata from backup file"""
        try:
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                with zipf.open('metadata.json') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Could not load backup metadata: {e}")
            return None
    
    def _verify_backup_integrity(self, backup_path: str, metadata: Dict[str, Any]) -> bool:
        """Verify backup file integrity by checking essential contents"""
        try:
            if "file_hash" not in metadata:
                return True  # Skip verification for backups without hash
            
            # Verify the backup contains expected files and structure
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                file_list = zipf.namelist()
                has_metadata = 'metadata.json' in file_list
                
                if not has_metadata:
                    self.logger.error("Backup missing metadata.json")
                    return False
                
                # Verify metadata content matches
                metadata_content = zipf.read('metadata.json')
                stored_metadata = json.loads(metadata_content.decode('utf-8'))
                
                # Check key fields match
                key_fields = ['backup_name', 'backup_type', 'timestamp']
                for field in key_fields:
                    if stored_metadata.get(field) != metadata.get(field):
                        self.logger.error(f"Metadata mismatch in field: {field}")
                        return False
                
                # Check backup type specific requirements
                backup_type = stored_metadata.get('backup_type')
                
                if backup_type == 'full':
                    # Full backups need database and JSON export
                    has_database = any(f.endswith('.db') for f in file_list)
                    has_json_export = 'data_export.json' in file_list
                    
                    if not (has_database and has_json_export):
                        self.logger.error("Full backup missing required files")
                        return False
                        
                elif backup_type == 'incremental':
                    # Incremental backups need changes file
                    has_changes = 'changes.json' in file_list
                    
                    if not has_changes:
                        self.logger.error("Incremental backup missing changes.json")
                        return False
                
                return True
                
        except Exception as e:
            self.logger.error(f"Integrity verification failed: {e}")
            return False
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _restore_full_backup(self, backup_path: str, metadata: Dict[str, Any], options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Restore from full backup"""
        try:
            # Extract backup to temporary directory
            temp_dir = self.backup_dir / f"restore_temp_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            temp_dir.mkdir(exist_ok=True)
            
            try:
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                # Check if database file exists in backup
                db_backup_path = temp_dir / "database.db"
                json_backup_path = temp_dir / "data_export.json"
                
                if db_backup_path.exists():
                    # Direct database file restore
                    shutil.copy2(db_backup_path, self.db_path)
                elif json_backup_path.exists():
                    # JSON data restore
                    with open(json_backup_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self._restore_from_json_data(data)
                else:
                    return {
                        "success": False,
                        "error": "No database or JSON data found in backup",
                        "message": "Backup file appears to be incomplete"
                    }
                
                return {
                    "success": True,
                    "message": f"Database restored successfully from {metadata['backup_name']}",
                    "restored_tables": metadata.get("tables_backed_up", []),
                    "restored_records": metadata.get("record_counts", {})
                }
                
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Full backup restore failed: {e}"
            }
    
    def _restore_incremental_backup(self, backup_path: str, metadata: Dict[str, Any], options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Restore from incremental backup"""
        try:
            # First, we need to restore the base backup
            base_backup_path = metadata.get("base_backup")
            if not base_backup_path or not os.path.exists(base_backup_path):
                return {
                    "success": False,
                    "error": "Base backup not found",
                    "message": f"Cannot restore incremental backup: base backup not found at {base_backup_path}"
                }
            
            # Restore base backup first
            base_metadata = self._load_backup_metadata(base_backup_path)
            if not base_metadata:
                return {
                    "success": False,
                    "error": "Invalid base backup",
                    "message": "Could not load base backup metadata"
                }
            
            # Restore the base backup
            base_restore_result = self._restore_full_backup(base_backup_path, base_metadata, options)
            if not base_restore_result.get("success"):
                return {
                    "success": False,
                    "error": "Base backup restore failed",
                    "message": f"Failed to restore base backup: {base_restore_result.get('message')}"
                }
            
            # Now apply incremental changes
            temp_dir = self.backup_dir / f"restore_inc_temp_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            temp_dir.mkdir(exist_ok=True)
            
            try:
                # Extract incremental backup
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                # Load changes
                changes_file = temp_dir / "changes.json"
                if not changes_file.exists():
                    return {
                        "success": False,
                        "error": "Changes file not found",
                        "message": "Incremental backup is missing changes data"
                    }
                
                with open(changes_file, 'r', encoding='utf-8') as f:
                    changes = json.load(f)
                
                # Apply changes to database
                self._apply_incremental_changes(changes)
                
                return {
                    "success": True,
                    "message": f"Incremental backup restored successfully from {metadata['backup_name']}",
                    "restored_tables": list(changes.get("table_data", {}).keys()),
                    "changes_applied": {
                        "new_tables": len(changes.get("new_tables", [])),
                        "modified_tables": len(changes.get("modified_tables", {})),
                        "deleted_tables": len(changes.get("deleted_tables", []))
                    }
                }
                
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Incremental backup restore failed: {e}"
            }
    
    def _apply_incremental_changes(self, changes: Dict[str, Any]) -> None:
        """Apply incremental changes to the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Handle deleted tables
            for table in changes.get("deleted_tables", []):
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")
                    self.logger.info(f"Dropped table: {table}")
                except sqlite3.Error as e:
                    self.logger.warning(f"Could not drop table {table}: {e}")
            
            # Handle table data changes
            table_data = changes.get("table_data", {})
            for table_name, table_info in table_data.items():
                action = table_info.get("action")
                data = table_info.get("data", [])
                
                if action == "create":
                    # For new tables, we assume they were created during base restore
                    # Just insert the data
                    self._insert_table_data(cursor, table_name, data)
                    self.logger.info(f"Created table {table_name} with {len(data)} records")
                    
                elif action == "update":
                    # For updated tables, replace all data
                    try:
                        cursor.execute(f"DELETE FROM {table_name}")
                        self._insert_table_data(cursor, table_name, data)
                        self.logger.info(f"Updated table {table_name} with {len(data)} records")
                    except sqlite3.Error as e:
                        self.logger.error(f"Could not update table {table_name}: {e}")
            
            conn.commit()
    
    def _insert_table_data(self, cursor, table_name: str, data: List[Dict]) -> None:
        """Insert data into a table"""
        if not data:
            return
        
        # Get column names from first record
        columns = list(data[0].keys())
        placeholders = ', '.join(['?' for _ in columns])
        column_names = ', '.join(columns)
        
        insert_sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"
        
        # Convert data to tuples
        rows = []
        for record in data:
            row = tuple(record.get(col) for col in columns)
            rows.append(row)
        
        cursor.executemany(insert_sql, rows)
    
    def _restore_from_json_data(self, data: Dict[str, List[Dict]]) -> None:
        """Restore database from JSON data"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Clear existing data (be careful!)
            for table_name in data.keys():
                try:
                    cursor.execute(f"DELETE FROM {table_name}")
                except sqlite3.Error:
                    pass  # Table might not exist
            
            # Insert data
            for table_name, records in data.items():
                if not records:
                    continue
                
                # Get column names from first record
                columns = list(records[0].keys())
                placeholders = ', '.join(['?' for _ in columns])
                
                insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
                
                for record in records:
                    values = [record[col] for col in columns]
                    try:
                        cursor.execute(insert_sql, values)
                    except sqlite3.Error as e:
                        self.logger.warning(f"Could not insert record into {table_name}: {e}")
            
            conn.commit()


# Example usage and testing
if __name__ == "__main__":
    backup_manager = DatabaseBackupManager()
    
    # Create a full backup
    result = backup_manager.create_full_backup("test_backup")
    print(f"Backup result: {result}")
    
    # List all backups
    backups = backup_manager.list_backups()
    print(f"Available backups: {len(backups)}")
    for backup in backups:
        print(f"  - {backup['file_name']} ({backup['file_size']} bytes)")
