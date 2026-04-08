import os

class FileRepository:
    def read_bytes(self, path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()
            
    def write_bytes(self, path: str, data: bytes) -> None:
        with open(path, "wb") as f:
            f.write(data)
            
    def file_exists(self, path: str) -> bool:
        return os.path.exists(path)
