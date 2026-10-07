{
    "name": "FACODI API",
    "summary": "Provider-backed API operations and webhook bridge for FACODI integrations",
    "version": "19.0.2.0.0",
    "category": "Productivity",
    "author": "FACODI",
    "depends": ["base", "web", "mail", "project", "website_slides"],
    "external_dependencies": {"python": ["youtube_transcript_api", "pypdf", "docx"]},
    "data": [
        "security/pipeline_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
