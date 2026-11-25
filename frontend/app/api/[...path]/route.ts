// The test page's way to the API: the page calls /api/<path>, and this forwards it to the backend with the API key
// from this server's environment (API_KEY), so the key never reaches the browser.

const API_URL = (process.env.API_URL || "http://localhost:8000").replace(/\/$/, "");

// The answer's headers the page needs: what it is, and the file name of a download.
const PASSED_ON = ["content-type", "content-disposition"];

async function forward(request: Request, { params }: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const key = process.env.API_KEY;
  if (!key) {
    return Response.json(
      { detail: "The test page has no API_KEY. start.sh passes it from .env; without it, set API_KEY in frontend/.env.local." },
      { status: 500 },
    );
  }
  const { path } = await params;
  const target = `${API_URL}/${path.map(encodeURIComponent).join("/")}${new URL(request.url).search}`;
  const headers: Record<string, string> = { "X-API-Key": key };
  const type = request.headers.get("content-type");
  if (type) headers["Content-Type"] = type;

  let answer: Response;
  try {
    answer = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "POST" ? await request.text() : undefined,
    });
  } catch {
    return Response.json({ detail: `The API at ${API_URL} cannot be reached. Is the backend running?` }, { status: 502 });
  }
  const passed = new Headers();
  for (const name of PASSED_ON) {
    const value = answer.headers.get(name);
    if (value) passed.set(name, value);
  }
  return new Response(answer.body, { status: answer.status, headers: passed });
}

export { forward as GET, forward as POST };
