import os
import re
import json
import hashlib
import subprocess
import tempfile
from flask import Blueprint, request, jsonify, Response, send_file
from Features.ClipBuilder.ClipBuilderBusinessService import ClipBuilderBusinessService, _ResolveFFmpegPath
from Repositories.DatabaseManager import DatabaseManager
from Core.Logging.LoggingService import LoggingService

ClipBuilderBlueprint = Blueprint('ClipBuilder', __name__, url_prefix='/api/ClipBuilder')

DEFAULT_FOLDERS = {
    60:  {"Primary": r"Z:\Videos\60Seconds",  "Half": r"Z:\Videos\30Seconds"},
    120: {"Primary": r"Z:\Videos\120Seconds", "Half": r"Z:\Videos\60Seconds"},
}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.webm', '.mov', '.m4v', '.wmv', '.flv', '.ts', '.mpg', '.mpeg'}


def _EnsureTables():
    """Create ClipBuilder tables if they don't exist."""
    Db = DatabaseManager()
    Db.DatabaseService.ExecuteNonQuery("""
        CREATE TABLE IF NOT EXISTS ClipBuilderPresets (
            Id SERIAL PRIMARY KEY,
            PresetName TEXT NOT NULL,
            FileId INTEGER,
            FileName TEXT,
            FilePath TEXT,
            ClipDuration REAL NOT NULL,
            TargetLength INTEGER DEFAULT 60,
            IncludeHalf BOOLEAN DEFAULT TRUE,
            StartTimes TEXT NOT NULL,
            OutputFolderPrimary TEXT,
            OutputFolderHalf TEXT,
            CreatedDate TIMESTAMP DEFAULT NOW()
        )
    """)
    Db.DatabaseService.ExecuteNonQuery("""
        CREATE TABLE IF NOT EXISTS ClipBuilderExports (
            Id SERIAL PRIMARY KEY,
            FileName TEXT NOT NULL,
            SourcePath TEXT NOT NULL,
            OutputPathPrimary TEXT,
            OutputPathHalf TEXT,
            ClipDuration REAL,
            TargetLength INTEGER,
            StartTimes TEXT,
            ExportedDate TIMESTAMP DEFAULT NOW()
        )
    """)
    # Migrate existing tables for schema changes
    try:
        Db.DatabaseService.ExecuteNonQuery("ALTER TABLE ClipBuilderExports ADD COLUMN IF NOT EXISTS OutputPathPrimary TEXT")
        Db.DatabaseService.ExecuteNonQuery("ALTER TABLE ClipBuilderExports ADD COLUMN IF NOT EXISTS OutputPathHalf TEXT")
        Db.DatabaseService.ExecuteNonQuery("ALTER TABLE ClipBuilderExports ADD COLUMN IF NOT EXISTS TargetLength INTEGER")
        Db.DatabaseService.ExecuteNonQuery("ALTER TABLE ClipBuilderPresets ADD COLUMN IF NOT EXISTS TargetLength INTEGER DEFAULT 60")
        Db.DatabaseService.ExecuteNonQuery("ALTER TABLE ClipBuilderPresets ADD COLUMN IF NOT EXISTS IncludeHalf BOOLEAN DEFAULT TRUE")
        Db.DatabaseService.ExecuteNonQuery("ALTER TABLE ClipBuilderPresets ADD COLUMN IF NOT EXISTS OutputFolderPrimary TEXT")
        Db.DatabaseService.ExecuteNonQuery("ALTER TABLE ClipBuilderPresets ADD COLUMN IF NOT EXISTS OutputFolderHalf TEXT")
    except Exception:
        pass


@ClipBuilderBlueprint.route('/StreamVideo', methods=['GET'])
def StreamVideo():
    """Stream a video file by FileId (DB lookup) or FilePath (direct) with Range support."""
    try:
        FileId = request.args.get('FileId')
        FilePath = request.args.get('FilePath')

        if FileId:
            Db = DatabaseManager()
            Rows = Db.DatabaseService.ExecuteQuery(
                "SELECT FilePath FROM MediaFiles WHERE Id = %s", (int(FileId),)
            )
            if not Rows:
                return jsonify({"Success": False, "ErrorMessage": "File not found"}), 404
            FilePath = Rows[0]['filepath']
        elif not FilePath:
            return jsonify({"Success": False, "ErrorMessage": "FileId or FilePath is required"}), 400

        if not FilePath or not os.path.exists(FilePath):
            return jsonify({"Success": False, "ErrorMessage": f"File not accessible: {FilePath}"}), 404

        FileSize = os.path.getsize(FilePath)
        Ext = os.path.splitext(FilePath)[1].lower()
        MimeMap = {'.mp4': 'video/mp4', '.mkv': 'video/x-matroska', '.avi': 'video/x-msvideo', '.webm': 'video/webm', '.mov': 'video/quicktime'}
        MimeType = MimeMap.get(Ext, 'video/mp4')

        RangeHeader = request.headers.get('Range')
        if RangeHeader:
            Match = re.search(r'bytes=(\d+)-(\d*)', RangeHeader)
            if Match:
                Start = int(Match.group(1))
                End = int(Match.group(2)) if Match.group(2) else FileSize - 1
                End = min(End, FileSize - 1)
                ChunkSize = End - Start + 1

                def Generate():
                    with open(FilePath, 'rb') as F:
                        F.seek(Start)
                        Remaining = ChunkSize
                        while Remaining > 0:
                            ReadSize = min(65536, Remaining)
                            Data = F.read(ReadSize)
                            if not Data:
                                break
                            Remaining -= len(Data)
                            yield Data

                return Response(
                    Generate(),
                    status=206,
                    mimetype=MimeType,
                    headers={
                        'Content-Range': f'bytes {Start}-{End}/{FileSize}',
                        'Accept-Ranges': 'bytes',
                        'Content-Length': str(ChunkSize),
                        'Content-Type': MimeType
                    }
                )

        # No Range header — stream entire file
        def GenerateFull():
            with open(FilePath, 'rb') as F:
                while True:
                    Data = F.read(65536)
                    if not Data:
                        break
                    yield Data

        return Response(
            GenerateFull(),
            status=200,
            mimetype=MimeType,
            headers={
                'Accept-Ranges': 'bytes',
                'Content-Length': str(FileSize),
                'Content-Type': MimeType
            }
        )

    except Exception as Ex:
        LoggingService.LogException("Error streaming video", Ex, "ClipBuilderController", "StreamVideo")
        return jsonify({"Success": False, "ErrorMessage": str(Ex)}), 500


@ClipBuilderBlueprint.route('/Export', methods=['POST'])
def Export():
    """Export clips from a video file. Supports configurable target length with optional half-length version."""
    try:
        Data = request.get_json() or {}
        FileId = Data.get('FileId')
        DirectPath = Data.get('FilePath')
        ClipDuration = Data.get('ClipDuration')
        StartTimes = Data.get('StartTimes', [])
        TargetLength = int(Data.get('TargetLength', 60))
        IncludeHalf = Data.get('IncludeHalf', True)
        Defaults = DEFAULT_FOLDERS.get(TargetLength, DEFAULT_FOLDERS[60])
        OutputFolderPrimary = Data.get('OutputFolderPrimary', Defaults['Primary'])
        OutputFolderHalf = Data.get('OutputFolderHalf', Defaults['Half'])

        if not ClipDuration or not StartTimes:
            return jsonify({"Success": False, "ErrorMessage": "ClipDuration and StartTimes are required"}), 400
        if not FileId and not DirectPath:
            return jsonify({"Success": False, "ErrorMessage": "FileId or FilePath is required"}), 400

        # Validate start times format (HH:MM:SS or seconds)
        for St in StartTimes:
            if not re.match(r'^(\d+:)?\d{1,2}:\d{2}(\.\d+)?$', str(St)) and not re.match(r'^\d+(\.\d+)?$', str(St)):
                return jsonify({"Success": False, "ErrorMessage": f"Invalid start time format: {St}"}), 400

        # Resolve file path — DB lookup or direct path
        if FileId:
            Db = DatabaseManager()
            Rows = Db.DatabaseService.ExecuteQuery(
                "SELECT FilePath, FileName FROM MediaFiles WHERE Id = %s", (int(FileId),)
            )
            if not Rows:
                return jsonify({"Success": False, "ErrorMessage": "File not found"}), 404
            FilePath = Rows[0]['filepath']
            FileName = Rows[0]['filename']
        else:
            FilePath = DirectPath
            FileName = os.path.basename(DirectPath)

        if not FilePath or not os.path.exists(FilePath):
            return jsonify({"Success": False, "ErrorMessage": f"File not accessible: {FilePath}"}), 404

        OutputName = os.path.splitext(FileName)[0] if FileName else "clip"

        # Build outputs: primary (1x) and optionally half (0.5x clip duration)
        Outputs = [
            (f"{TargetLength}s", 1, OutputFolderPrimary),
        ]
        if IncludeHalf:
            HalfLength = TargetLength // 2
            Outputs.append((f"{HalfLength}s", 0.5, OutputFolderHalf))

        Service = ClipBuilderBusinessService()
        Result = Service.ExtractAndConcatenate(FilePath, StartTimes, float(ClipDuration), Outputs, OutputName)

        if Result.get("Success"):
            # Record the export
            try:
                _EnsureTables()
                Db2 = DatabaseManager()
                Paths = Result["OutputPaths"]
                Db2.DatabaseService.ExecuteNonQuery(
                    """INSERT INTO ClipBuilderExports (FileName, SourcePath, OutputPathPrimary, OutputPathHalf, ClipDuration, TargetLength, StartTimes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (FileName, FilePath, Paths[0] if len(Paths) > 0 else None,
                     Paths[1] if len(Paths) > 1 else None, float(ClipDuration), TargetLength, json.dumps(StartTimes))
                )
            except Exception as RecordEx:
                LoggingService.LogException("Failed to record export", RecordEx, "ClipBuilderController", "Export")
            return jsonify({"Success": True, "OutputPaths": Result["OutputPaths"]}), 200
        else:
            return jsonify(Result), 500

    except Exception as Ex:
        LoggingService.LogException("Error in Export", Ex, "ClipBuilderController", "Export")
        return jsonify({"Success": False, "ErrorMessage": str(Ex)}), 500


# --- Presets ---

@ClipBuilderBlueprint.route('/Presets', methods=['GET'])
def GetPresets():
    """List all saved presets."""
    try:
        _EnsureTables()
        Db = DatabaseManager()
        Rows = Db.DatabaseService.ExecuteQuery(
            "SELECT Id, PresetName, FileId, FileName, ClipDuration, CreatedDate FROM ClipBuilderPresets ORDER BY CreatedDate DESC"
        )
        Presets = []
        for Row in Rows:
            Presets.append({
                'Id': Row['id'],
                'PresetName': Row['presetname'],
                'FileId': Row['fileid'],
                'FileName': Row['filename'],
                'ClipDuration': Row['clipduration'],
                'CreatedDate': str(Row['createddate']) if Row['createddate'] else None
            })
        return jsonify({"Success": True, "Presets": Presets}), 200
    except Exception as Ex:
        LoggingService.LogException("Error listing presets", Ex, "ClipBuilderController", "GetPresets")
        return jsonify({"Success": False, "ErrorMessage": str(Ex)}), 500


@ClipBuilderBlueprint.route('/Preset', methods=['GET'])
def LoadPreset():
    """Load a single preset by Id."""
    try:
        PresetId = request.args.get('Id')
        if not PresetId:
            return jsonify({"Success": False, "ErrorMessage": "Id is required"}), 400

        _EnsureTables()
        Db = DatabaseManager()
        Rows = Db.DatabaseService.ExecuteQuery(
            "SELECT * FROM ClipBuilderPresets WHERE Id = %s", (int(PresetId),)
        )
        if not Rows:
            return jsonify({"Success": False, "ErrorMessage": "Preset not found"}), 404

        Row = Rows[0]
        TL = Row.get('targetlength', 60) or 60
        Defaults = DEFAULT_FOLDERS.get(TL, DEFAULT_FOLDERS[60])
        return jsonify({
            "Success": True,
            "Preset": {
                'Id': Row['id'],
                'PresetName': Row['presetname'],
                'FileId': Row['fileid'],
                'FileName': Row['filename'],
                'FilePath': Row['filepath'],
                'ClipDuration': Row['clipduration'],
                'TargetLength': TL,
                'IncludeHalf': Row.get('includehalf', True),
                'StartTimes': json.loads(Row['starttimes']),
                'OutputFolderPrimary': Row.get('outputfolderprimary') or Defaults['Primary'],
                'OutputFolderHalf': Row.get('outputfolderhalf') or Defaults['Half']
            }
        }), 200
    except Exception as Ex:
        LoggingService.LogException("Error loading preset", Ex, "ClipBuilderController", "LoadPreset")
        return jsonify({"Success": False, "ErrorMessage": str(Ex)}), 500


@ClipBuilderBlueprint.route('/Preset', methods=['POST'])
def SavePreset():
    """Save current settings as a preset."""
    try:
        Data = request.get_json() or {}
        PresetName = Data.get('PresetName', '').strip()
        if not PresetName:
            return jsonify({"Success": False, "ErrorMessage": "PresetName is required"}), 400

        FileId = Data.get('FileId')
        FileName = Data.get('FileName', '')
        FilePath = Data.get('FilePath', '')
        ClipDuration = Data.get('ClipDuration')
        TargetLength = int(Data.get('TargetLength', 60))
        IncludeHalf = Data.get('IncludeHalf', True)
        StartTimes = Data.get('StartTimes', [])
        Defaults = DEFAULT_FOLDERS.get(TargetLength, DEFAULT_FOLDERS[60])
        OutputFolderPrimary = Data.get('OutputFolderPrimary', Defaults['Primary'])
        OutputFolderHalf = Data.get('OutputFolderHalf', Defaults['Half'])

        if not ClipDuration or not StartTimes:
            return jsonify({"Success": False, "ErrorMessage": "ClipDuration and StartTimes are required"}), 400

        _EnsureTables()
        Db = DatabaseManager()
        Db.DatabaseService.ExecuteNonQuery(
            """INSERT INTO ClipBuilderPresets (PresetName, FileId, FileName, FilePath, ClipDuration, TargetLength, IncludeHalf, StartTimes, OutputFolderPrimary, OutputFolderHalf)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (PresetName, FileId, FileName, FilePath, float(ClipDuration), TargetLength, IncludeHalf, json.dumps(StartTimes), OutputFolderPrimary, OutputFolderHalf)
        )
        return jsonify({"Success": True, "Message": "Preset saved"}), 200
    except Exception as Ex:
        LoggingService.LogException("Error saving preset", Ex, "ClipBuilderController", "SavePreset")
        return jsonify({"Success": False, "ErrorMessage": str(Ex)}), 500


@ClipBuilderBlueprint.route('/Preset', methods=['DELETE'])
def DeletePreset():
    """Delete a preset by Id."""
    try:
        PresetId = request.args.get('Id')
        if not PresetId:
            return jsonify({"Success": False, "ErrorMessage": "Id is required"}), 400

        _EnsureTables()
        Db = DatabaseManager()
        Db.DatabaseService.ExecuteNonQuery(
            "DELETE FROM ClipBuilderPresets WHERE Id = %s", (int(PresetId),)
        )
        return jsonify({"Success": True, "Message": "Preset deleted"}), 200
    except Exception as Ex:
        LoggingService.LogException("Error deleting preset", Ex, "ClipBuilderController", "DeletePreset")
        return jsonify({"Success": False, "ErrorMessage": str(Ex)}), 500


# --- Waveform ---

WAVEFORM_CACHE_DIR = os.path.join(tempfile.gettempdir(), "clipbuilder_waveforms")


@ClipBuilderBlueprint.route('/Waveform', methods=['GET'])
def Waveform():
    """Generate and return an audio waveform PNG for a video file. Cached by file path."""
    try:
        FileId = request.args.get('FileId')
        DirectPath = request.args.get('FilePath')

        if FileId:
            Db = DatabaseManager()
            Rows = Db.DatabaseService.ExecuteQuery(
                "SELECT FilePath FROM MediaFiles WHERE Id = %s", (int(FileId),)
            )
            if not Rows:
                return jsonify({"Success": False, "ErrorMessage": "File not found"}), 404
            FilePath = Rows[0]['filepath']
        elif DirectPath:
            FilePath = DirectPath
        else:
            return jsonify({"Success": False, "ErrorMessage": "FileId or FilePath required"}), 400

        if not FilePath or not os.path.exists(FilePath):
            return jsonify({"Success": False, "ErrorMessage": f"File not accessible: {FilePath}"}), 404

        # Check cache
        os.makedirs(WAVEFORM_CACHE_DIR, exist_ok=True)
        PathHash = hashlib.md5(FilePath.encode()).hexdigest()
        CachePath = os.path.join(WAVEFORM_CACHE_DIR, f"{PathHash}.png")

        if not os.path.exists(CachePath):
            Cmd = [
                _ResolveFFmpegPath(),
                "-i", FilePath,
                "-filter_complex",
                "aformat=channel_layouts=mono,showwavespic=s=1600x120:colors=#0d6efd50|#0d6efd",
                "-frames:v", "1",
                "-y", CachePath
            ]
            Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=120)
            if Result.returncode != 0:
                return jsonify({"Success": False, "ErrorMessage": f"Waveform generation failed: {Result.stderr[-300:]}"}), 500

        return send_file(CachePath, mimetype='image/png')

    except Exception as Ex:
        LoggingService.LogException("Error generating waveform", Ex, "ClipBuilderController", "Waveform")
        return jsonify({"Success": False, "ErrorMessage": str(Ex)}), 500


THUMBNAIL_CACHE_DIR = os.path.join(tempfile.gettempdir(), "clipbuilder_thumbnails")


@ClipBuilderBlueprint.route('/Thumbnail', methods=['GET'])
def Thumbnail():
    """Extract a single frame at a given timestamp and return as JPEG."""
    try:
        FileId = request.args.get('FileId')
        DirectPath = request.args.get('FilePath')
        Time = request.args.get('Time', '0')

        if FileId:
            Db = DatabaseManager()
            Rows = Db.DatabaseService.ExecuteQuery(
                "SELECT FilePath FROM MediaFiles WHERE Id = %s", (int(FileId),)
            )
            if not Rows:
                return jsonify({"Success": False, "ErrorMessage": "File not found"}), 404
            FilePath = Rows[0]['filepath']
        elif DirectPath:
            FilePath = DirectPath
        else:
            return jsonify({"Success": False, "ErrorMessage": "FileId or FilePath required"}), 400

        if not FilePath or not os.path.exists(FilePath):
            return jsonify({"Success": False, "ErrorMessage": f"File not accessible: {FilePath}"}), 404

        os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
        CacheKey = hashlib.md5(f"{FilePath}@{Time}".encode()).hexdigest()
        CachePath = os.path.join(THUMBNAIL_CACHE_DIR, f"{CacheKey}.jpg")

        if not os.path.exists(CachePath):
            Cmd = [
                _ResolveFFmpegPath(),
                "-ss", str(Time),
                "-i", FilePath,
                "-frames:v", "1",
                "-vf", "scale=160:-1",
                "-q:v", "4",
                "-y", CachePath
            ]
            Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=30)
            if Result.returncode != 0:
                return jsonify({"Success": False, "ErrorMessage": "Thumbnail extraction failed"}), 500

        return send_file(CachePath, mimetype='image/jpeg')

    except Exception as Ex:
        LoggingService.LogException("Error generating thumbnail", Ex, "ClipBuilderController", "Thumbnail")
        return jsonify({"Success": False, "ErrorMessage": str(Ex)}), 500


# --- Export History ---

@ClipBuilderBlueprint.route('/CheckExported', methods=['GET'])
def CheckExported():
    """Check if a source file has been exported before. Accepts FilePath or FileName."""
    try:
        _EnsureTables()
        SourcePath = request.args.get('FilePath', '')
        FileName = request.args.get('FileName', '')

        Db = DatabaseManager()
        if SourcePath:
            Rows = Db.DatabaseService.ExecuteQuery(
                "SELECT Id, ExportedDate, OutputPathPrimary, OutputPathHalf FROM ClipBuilderExports WHERE SourcePath = %s ORDER BY ExportedDate DESC",
                (SourcePath,)
            )
        elif FileName:
            Rows = Db.DatabaseService.ExecuteQuery(
                "SELECT Id, ExportedDate, OutputPathPrimary, OutputPathHalf FROM ClipBuilderExports WHERE FileName = %s ORDER BY ExportedDate DESC",
                (FileName,)
            )
        else:
            return jsonify({"Success": True, "Exported": False, "Exports": []}), 200

        Exports = []
        for Row in Rows:
            Exports.append({
                'Id': Row['id'],
                'ExportedDate': str(Row['exporteddate']) if Row['exporteddate'] else None,
                'OutputPathPrimary': Row.get('outputpathprimary'),
                'OutputPathHalf': Row.get('outputpathhalf')
            })
        return jsonify({"Success": True, "Exported": len(Exports) > 0, "Exports": Exports}), 200
    except Exception as Ex:
        LoggingService.LogException("Error checking exports", Ex, "ClipBuilderController", "CheckExported")
        return jsonify({"Success": False, "ErrorMessage": str(Ex)}), 500


@ClipBuilderBlueprint.route('/ExportHistory', methods=['GET'])
def ExportHistory():
    """List all exports, most recent first."""
    try:
        _EnsureTables()
        Db = DatabaseManager()
        Rows = Db.DatabaseService.ExecuteQuery(
            "SELECT Id, FileName, SourcePath, OutputPathPrimary, OutputPathHalf, ClipDuration, TargetLength, ExportedDate FROM ClipBuilderExports ORDER BY ExportedDate DESC LIMIT 100"
        )
        Exports = []
        for Row in Rows:
            Exports.append({
                'Id': Row['id'],
                'FileName': Row['filename'],
                'SourcePath': Row['sourcepath'],
                'OutputPathPrimary': Row.get('outputpathprimary'),
                'OutputPathHalf': Row.get('outputpathhalf'),
                'ClipDuration': Row['clipduration'],
                'TargetLength': Row.get('targetlength'),
                'ExportedDate': str(Row['exporteddate']) if Row['exporteddate'] else None
            })
        return jsonify({"Success": True, "Exports": Exports}), 200
    except Exception as Ex:
        LoggingService.LogException("Error listing export history", Ex, "ClipBuilderController", "ExportHistory")
        return jsonify({"Success": False, "ErrorMessage": str(Ex)}), 500


# --- Browse ---

@ClipBuilderBlueprint.route('/Browse', methods=['GET'])
def Browse():
    """List folders and video files at a given path. Optional Filter for starts-with (case-insensitive)."""
    try:
        Path = request.args.get('Path', '')
        Filter = request.args.get('Filter', '').strip().lower()
        Scan = request.args.get('Scan', '').lower() == 'true'

        # Default to listing drive roots on Windows
        if not Path:
            import string
            Drives = []
            for Letter in string.ascii_uppercase:
                DrivePath = f"{Letter}:\\"
                if os.path.exists(DrivePath):
                    Drives.append({"Name": DrivePath, "Path": DrivePath, "Type": "folder"})
            return jsonify({"Success": True, "Path": "", "Items": Drives}), 200

        if not os.path.isdir(Path):
            return jsonify({"Success": False, "ErrorMessage": f"Not a directory: {Path}"}), 400

        Items = []

        if Scan and Filter:
            # Recursive scan — find all video files whose name starts with Filter
            MaxResults = 200
            for Root, Dirs, Files in os.walk(Path):
                for FileName in Files:
                    if not FileName.lower().startswith(Filter):
                        continue
                    Ext = os.path.splitext(FileName)[1].lower()
                    if Ext not in VIDEO_EXTENSIONS:
                        continue
                    FullPath = os.path.join(Root, FileName)
                    try:
                        SizeMB = round(os.path.getsize(FullPath) / (1024 * 1024), 1)
                    except OSError:
                        SizeMB = 0
                    Items.append({"Name": FileName, "Path": FullPath, "Type": "file", "SizeMB": SizeMB,
                                  "Directory": Root})
                    if len(Items) >= MaxResults:
                        break
                if len(Items) >= MaxResults:
                    break
            Items.sort(key=lambda I: I['Name'].lower())
        else:
            # Normal single-directory listing
            try:
                Entries = sorted(os.scandir(Path), key=lambda E: (not E.is_dir(), E.name.lower()))
            except PermissionError:
                return jsonify({"Success": False, "ErrorMessage": f"Permission denied: {Path}"}), 403

            for Entry in Entries:
                try:
                    if Entry.is_dir(follow_symlinks=False):
                        if not Filter or Entry.name.lower().startswith(Filter):
                            Items.append({"Name": Entry.name, "Path": Entry.path, "Type": "folder"})
                    elif Entry.is_file():
                        Ext = os.path.splitext(Entry.name)[1].lower()
                        if Ext in VIDEO_EXTENSIONS:
                            if not Filter or Entry.name.lower().startswith(Filter):
                                SizeMB = round(Entry.stat().st_size / (1024 * 1024), 1)
                                Items.append({"Name": Entry.name, "Path": Entry.path, "Type": "file", "SizeMB": SizeMB})
                except (PermissionError, OSError):
                    continue

        return jsonify({"Success": True, "Path": Path, "Parent": os.path.dirname(Path), "Items": Items}), 200
    except Exception as Ex:
        LoggingService.LogException("Error browsing", Ex, "ClipBuilderController", "Browse")
        return jsonify({"Success": False, "ErrorMessage": str(Ex)}), 500
