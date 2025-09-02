export default function handler(req, res) {
  // Redirect all requests to our Cloud Run service
  const targetUrl = `https://tobedtakip-90863126066.europe-west1.run.app${req.url}`;
  
  res.writeHead(302, {
    Location: targetUrl
  });
  res.end();
} 