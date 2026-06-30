from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import uuid

router = APIRouter(prefix="/jira", tags=["Jira"])

@router.post("/rest/api/2/issue")
async def create_jira_issue(request: Request):
    """
    Mock Jira Create Issue Endpoint.
    Dựa trên schema thực tế của Jira:
    - Nhận: POST request với body chứa { "fields": { "project", "summary", "description", "issuetype" } }
    - Trả về: HTTP 201 Created với format { "id", "key", "self" }
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"errorMessages": ["Invalid JSON"]})
        
    fields = data.get("fields")
    if not isinstance(fields, dict):
        return JSONResponse(status_code=400, content={"errorMessages": ["Field 'fields' is required and must be an object."]})

    # Bắt buộc phải có project.key
    project = fields.get("project")
    if not isinstance(project, dict) or not project.get("key"):
        return JSONResponse(status_code=400, content={"errors": {"project": "Project key is required"}})
    project_key = project["key"]

    # Bắt buộc phải có summary
    summary = fields.get("summary")
    if not summary:
        return JSONResponse(status_code=400, content={"errors": {"summary": "You must specify a summary of the issue."}})

    # Bắt buộc phải có description
    description = fields.get("description")
    if not description:
        return JSONResponse(status_code=400, content={"errors": {"description": "Description is required."}})

    # Bắt buộc phải có issuetype.name
    issuetype = fields.get("issuetype")
    if not isinstance(issuetype, dict) or not issuetype.get("name"):
        return JSONResponse(status_code=400, content={"errors": {"issuetype": "Specify a valid issue type"}})
        
    # Sinh ngẫu nhiên ID ticket
    ticket_id = f"{project_key}-{uuid.uuid4().hex[:4].upper()}"
    
    # In ra log để bạn dễ theo dõi khi debug
    print(f"✅ [MOCK JIRA] TICKET CREATED: {ticket_id} - Summary: {fields.get('summary')}")
    
    return JSONResponse(
        status_code=201,
        content={
            "id": "10000",
            "key": ticket_id,
            "self": f"http://simulator:8080/jira/rest/api/2/issue/10000"
        }
    )
