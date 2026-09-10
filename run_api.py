from config import API_HOST, API_PORT
from api_server import create_app
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(create_app(), host=API_HOST, port=API_PORT, log_level='info')
