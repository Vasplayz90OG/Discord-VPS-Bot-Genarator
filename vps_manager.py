# vps_manager.py
import os
import uuid
import random
import string

BACKEND = os.getenv("BACKEND", "mock")  # "mock" or "docker"
HOST_IP = os.getenv("HOST_IP", "127.0.0.1")  # public IP for real docker host
SSH_BASE_PORT = int(os.getenv("SSH_BASE_PORT", "22000"))
CREDITS = os.getenv("CREDITS", "Vasplayz90")

_STORE = {}

def _rand_password(n=12):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(n))

# ---------------- MOCK ----------------
def _create_mock(owner_id: str, os_image: str, ram: str, disk: str):
    vid = uuid.uuid4().hex[:8]
    port = SSH_BASE_PORT + random.randint(1, 1000)
    pwd = _rand_password()
    info = {"id": vid, "ip": HOST_IP, "ssh_port": port, "username": "root", "password": pwd, "backend": "mock"}
    _STORE[vid] = info
    return info

def _delete_mock(vid: str):
    return _STORE.pop(vid, None) is not None

# ---------------- DOCKER (real) ----------------
if BACKEND == "docker":
    import docker
    client = docker.from_env()

    def _create_docker(owner_id: str, os_image: str, ram: str, disk: str):
        vid = uuid.uuid4().hex[:8]
        host_port = SSH_BASE_PORT + random.randint(1, 1000)
        password = _rand_password()
        env = {"PASSWORD": password}
        # Try to pull (best-effort)
        try:
            client.images.pull(os_image)
        except Exception:
            pass
        # Run container; container must expose SSH on 22
        container = client.containers.run(
            image=os_image,
            detach=True,
            tty=True,
            labels={"vps_id": vid, "owner": owner_id, "credits": CREDITS},
            ports={"22/tcp": host_port},
            mem_limit=ram if ram else None,
            environment=env
        )
        # Best-effort set root password (may fail on some images)
        try:
            exec_id = client.api.exec_create(container.id, cmd=f"bash -lc 'echo root:{password} | chpasswd || true'")
            client.api.exec_start(exec_id)
        except Exception:
            pass
        info = {"id": vid, "ip": HOST_IP, "ssh_port": host_port, "username": "root", "password": password, "backend": "docker", "container_id": container.id}
        _STORE[vid] = info
        return info

    def _delete_docker(vid: str):
        info = _STORE.get(vid)
        if not info:
            return False
        cid = info.get("container_id")
        try:
            c = client.containers.get(cid)
            c.stop()
            c.remove()
        except Exception:
            pass
        _STORE.pop(vid, None)
        return True

# Public API
def create_vps(owner_id: str, os_image: str, ram: str, disk: str):
    if BACKEND == "mock":
        return _create_mock(owner_id, os_image, ram, disk)
    elif BACKEND == "docker":
        return _create_docker(owner_id, os_image, ram, disk)
    else:
        raise RuntimeError("Unknown BACKEND")

def delete_vps(vid: str):
    if BACKEND == "mock":
        return _delete_mock(vid)
    elif BACKEND == "docker":
        return _delete_docker(vid)
    else:
        return False

def list_vps():
    return list(_STORE.keys())

def get_vps_info(vid: str):
    return _STORE.get(vid)
