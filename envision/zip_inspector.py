"""
Zenodo ZIP Content Inspector
============================
Three approaches to inspect ZIP file contents from Zenodo without downloading everything:

1. SCRAPE THE PREVIEW PAGE - Parse the HTML preview that Zenodo generates
2. HTTP RANGE REQUESTS - Download only the ZIP central directory (file listing at end of archive)
3. FULL DOWNLOAD + INSPECT - For small files, just download and list

Author: Claude (for Jamey)
"""

import requests
from bs4 import BeautifulSoup
import struct
import io
import zipfile
from typing import Optional
import json


class ZenodoInspector:
    """Inspect Zenodo records and their ZIP file contents."""

    BASE_URL = "https://zenodo.org"
    API_URL = "https://zenodo.org/api/records"

    def __init__(self, record_id: str):
        self.record_id = record_id
        self.metadata = None
        self.files = []

    def fetch_metadata(self) -> dict:
        """Fetch record metadata via REST API."""
        resp = requests.get(f"{self.API_URL}/{self.record_id}")
        resp.raise_for_status()
        self.metadata = resp.json()

        # Extract file info
        self.files = self.metadata.get("files", [])
        return self.metadata

    def list_files(self) -> list[dict]:
        """List all files in the record with their metadata."""
        if not self.metadata:
            self.fetch_metadata()

        file_info = []
        for f in self.files:
            file_info.append(
                {
                    "filename": f.get("key"),
                    "size_bytes": f.get("size"),
                    "size_human": self._human_size(f.get("size", 0)),
                    "checksum": f.get("checksum"),
                    "download_url": f.get("links", {}).get("self"),
                }
            )
        return file_info

    # =========================================================================
    # APPROACH 1: Scrape the HTML preview page
    # =========================================================================
    def scrape_zip_preview(self, filename: str) -> Optional[list[str]]:
        """
        Scrape the Zenodo preview page to get ZIP contents.
        This is what you see when you click "Preview" on a ZIP file.

        Returns list of file paths inside the ZIP, or None if preview unavailable.
        """
        preview_url = f"{self.BASE_URL}/records/{self.record_id}/preview/{filename}"

        try:
            resp = requests.get(preview_url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"Failed to fetch preview: {e}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # The ZIP preview uses a tree structure - look for file entries
        # This may need adjustment based on current Zenodo HTML structure
        files = []

        # Try various selectors that Zenodo might use
        for selector in [".tree-item", ".file-item", "[data-filename]", "li.file"]:
            items = soup.select(selector)
            if items:
                for item in items:
                    text = item.get_text(strip=True)
                    if text:
                        files.append(text)
                break

        # Fallback: look for any nested list structure
        if not files:
            for li in soup.find_all("li"):
                text = li.get_text(strip=True)
                # Filter out obvious non-file entries
                if text and not text.startswith(("Preview", "Download", "View")):
                    files.append(text)

        return files if files else None

    # =========================================================================
    # APPROACH 2: HTTP Range requests to read ZIP central directory
    # =========================================================================
    def inspect_zip_via_range(
        self, filename: str, max_tail_bytes: int = 65536
    ) -> Optional[list[dict]]:
        """
        Use HTTP Range requests to download only the ZIP central directory.

        ZIP files store the file listing (central directory) at the END of the file,
        so we can download just the last ~64KB to get the complete file manifest
        without downloading the entire archive.

        Returns list of dicts with filename, compressed_size, uncompressed_size.
        """
        # Find the download URL for this file
        download_url = None
        for f in self.files:
            if f.get("key") == filename:
                download_url = f.get("links", {}).get("self")
                file_size = f.get("size", 0)
                break

        if not download_url:
            print(f"File '{filename}' not found in record")
            return None

        # Request the last N bytes using Range header
        headers = {"Range": f"bytes=-{max_tail_bytes}"}

        try:
            resp = requests.get(download_url, headers=headers, timeout=60)
            # 206 = Partial Content (range request successful)
            # 200 = Full content (server ignored range, file smaller than range)
            if resp.status_code not in (200, 206):
                print(f"Range request failed with status {resp.status_code}")
                return None
        except requests.RequestException as e:
            print(f"Request failed: {e}")
            return None

        # Parse the ZIP central directory from the downloaded bytes
        return self._parse_zip_central_directory(resp.content)

    def _parse_zip_central_directory(self, data: bytes) -> Optional[list[dict]]:
        """
        Parse ZIP central directory to extract file listing.

        ZIP structure (simplified):
        - [Local file headers + compressed data] ...
        - [Central directory] <-- file listing lives here
        - [End of central directory record]
        """
        # Find End of Central Directory (EOCD) signature: 0x06054b50
        eocd_sig = b"\x50\x4b\x05\x06"
        eocd_pos = data.rfind(eocd_sig)

        if eocd_pos == -1:
            print("Could not find ZIP end-of-central-directory signature")
            return None

        try:
            # Parse EOCD to find central directory location
            # EOCD structure (22 bytes minimum):
            # 4: signature, 2: disk number, 2: disk with CD,
            # 2: entries on disk, 2: total entries, 4: CD size, 4: CD offset, 2: comment length
            eocd = data[eocd_pos : eocd_pos + 22]
            total_entries = struct.unpack("<H", eocd[10:12])[0]
            cd_size = struct.unpack("<I", eocd[12:16])[0]
            cd_offset_in_file = struct.unpack("<I", eocd[16:20])[0]

            # Calculate where CD starts in our downloaded chunk
            # (Our chunk is the tail of the file)
            cd_start_in_chunk = eocd_pos - cd_size

            if cd_start_in_chunk < 0:
                print(
                    f"Central directory larger than downloaded chunk. Need more bytes."
                )
                return None

            # Parse central directory entries
            files = []
            pos = cd_start_in_chunk

            for _ in range(total_entries):
                if pos + 46 > len(data):
                    break

                # Central directory file header signature: 0x02014b50
                sig = data[pos : pos + 4]
                if sig != b"\x50\x4b\x01\x02":
                    break

                # Parse header
                compressed_size = struct.unpack("<I", data[pos + 20 : pos + 24])[0]
                uncompressed_size = struct.unpack("<I", data[pos + 24 : pos + 28])[0]
                filename_len = struct.unpack("<H", data[pos + 28 : pos + 30])[0]
                extra_len = struct.unpack("<H", data[pos + 30 : pos + 32])[0]
                comment_len = struct.unpack("<H", data[pos + 32 : pos + 34])[0]

                # Extract filename
                filename_bytes = data[pos + 46 : pos + 46 + filename_len]
                try:
                    filename = filename_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    filename = filename_bytes.decode("cp437", errors="replace")

                files.append(
                    {
                        "filename": filename,
                        "compressed_size": compressed_size,
                        "uncompressed_size": uncompressed_size,
                        "is_directory": filename.endswith("/"),
                    }
                )

                # Move to next entry
                pos += 46 + filename_len + extra_len + comment_len

            return files

        except Exception as e:
            print(f"Error parsing ZIP central directory: {e}")
            return None

    # =========================================================================
    # APPROACH 3: Full download for small files
    # =========================================================================
    def download_and_list_zip(
        self, filename: str, max_size_mb: int = 100
    ) -> Optional[list[dict]]:
        """
        Download the entire ZIP and list contents using zipfile.
        Only use for files under max_size_mb.
        """
        download_url = None
        file_size = 0

        for f in self.files:
            if f.get("key") == filename:
                download_url = f.get("links", {}).get("self")
                file_size = f.get("size", 0)
                break

        if not download_url:
            print(f"File '{filename}' not found")
            return None

        size_mb = file_size / (1024 * 1024)
        if size_mb > max_size_mb:
            print(f"File too large ({size_mb:.1f} MB > {max_size_mb} MB limit)")
            return None

        print(f"Downloading {filename} ({size_mb:.1f} MB)...")
        resp = requests.get(download_url, timeout=300)
        resp.raise_for_status()

        # Use zipfile to list contents
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            files = []
            for info in zf.infolist():
                files.append(
                    {
                        "filename": info.filename,
                        "compressed_size": info.compress_size,
                        "uncompressed_size": info.file_size,
                        "is_directory": info.is_dir(),
                    }
                )
            return files

    # =========================================================================
    # Utility methods
    # =========================================================================
    def _human_size(self, size_bytes: int) -> str:
        """Convert bytes to human-readable format."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"

    def summarize_zip_contents(self, contents: list[dict]) -> dict:
        """Generate summary statistics from ZIP contents."""
        if not contents:
            return {}

        extensions = {}
        total_files = 0
        total_dirs = 0
        total_size = 0

        for item in contents:
            if item.get("is_directory"):
                total_dirs += 1
            else:
                total_files += 1
                total_size += item.get("uncompressed_size", 0)

                # Count extensions
                filename = item.get("filename", "")
                if "." in filename:
                    ext = filename.rsplit(".", 1)[-1].lower()
                    extensions[ext] = extensions.get(ext, 0) + 1

        return {
            "total_files": total_files,
            "total_directories": total_dirs,
            "total_uncompressed_size": self._human_size(total_size),
            "file_types": dict(sorted(extensions.items(), key=lambda x: -x[1])[:20]),
        }


def screen_zenodo_dataset(record_id: str) -> dict:
    """
    Convenience function to screen a Zenodo dataset.
    Returns metadata and ZIP contents for any ZIP files found.
    """
    inspector = ZenodoInspector(record_id)

    result = {
        "record_id": record_id,
        "url": f"https://zenodo.org/records/{record_id}",
        "metadata": None,
        "files": [],
        "zip_contents": {},
    }

    # Fetch metadata
    try:
        metadata = inspector.fetch_metadata()
        result["metadata"] = {
            "title": metadata.get("metadata", {}).get("title"),
            "description": metadata.get("metadata", {}).get("description", "")[:500],
            "creators": [
                c.get("name") for c in metadata.get("metadata", {}).get("creators", [])
            ],
            "keywords": metadata.get("metadata", {}).get("keywords", []),
            "license": metadata.get("metadata", {}).get("license", {}).get("id"),
            "publication_date": metadata.get("metadata", {}).get("publication_date"),
        }
    except Exception as e:
        result["error"] = f"Failed to fetch metadata: {e}"
        return result

    # List files
    result["files"] = inspector.list_files()

    # Inspect ZIP files
    for f in result["files"]:
        filename = f["filename"]
        if filename.lower().endswith(".zip"):
            print(f"\nInspecting ZIP: {filename}")

            # Try range request first (fastest for large files)
            contents = inspector.inspect_zip_via_range(filename)

            if contents:
                result["zip_contents"][filename] = {
                    "method": "range_request",
                    "contents": contents,
                    "summary": inspector.summarize_zip_contents(contents),
                }
            else:
                # Fall back to scraping preview
                print("  Range request failed, trying preview scrape...")
                preview = inspector.scrape_zip_preview(filename)
                if preview:
                    result["zip_contents"][filename] = {
                        "method": "preview_scrape",
                        "contents": preview,
                    }
                else:
                    result["zip_contents"][filename] = {
                        "method": "failed",
                        "note": "Could not inspect without full download",
                    }

    return result


# =============================================================================
# Demo / CLI usage
# =============================================================================
if __name__ == "__main__":
    import sys

    # Example usage with one of your datasets
    test_records = [
        "8254022",  # PT-OCT ANN Project (302 MB)
        "1464026",  # OCTSEG (5.6 MB)
    ]

    record_id = sys.argv[1] if len(sys.argv) > 1 else test_records[0]

    print(f"Screening Zenodo record: {record_id}")
    print("=" * 60)

    result = screen_zenodo_dataset(record_id)

    print(f"\nTitle: {result['metadata']['title']}")
    print(f"Files: {len(result['files'])}")

    for f in result["files"]:
        print(f"  - {f['filename']} ({f['size_human']})")

    if result["zip_contents"]:
        print("\nZIP Contents:")
        for zip_name, info in result["zip_contents"].items():
            print(f"\n  {zip_name} (method: {info['method']})")
            if "summary" in info:
                summary = info["summary"]
                print(
                    f"    Files: {summary['total_files']}, Dirs: {summary['total_directories']}"
                )
                print(f"    Total size: {summary['total_uncompressed_size']}")
                print(f"    Types: {summary['file_types']}")
            elif "contents" in info and isinstance(info["contents"], list):
                # Show first 10 entries
                for item in info["contents"][:10]:
                    if isinstance(item, dict):
                        print(f"    - {item['filename']}")
                    else:
                        print(f"    - {item}")
                if len(info["contents"]) > 10:
                    print(f"    ... and {len(info['contents']) - 10} more")
