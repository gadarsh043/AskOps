// AskOps frontend configuration
// Override ASKOPS_API_URL via Netlify environment injection for production
window.ASKOPS_API = window.ASKOPS_API_URL || 'http://localhost:5678';
window.DEMO_WORKSPACE_ID = '00000000-0000-0000-0000-000000000001';
