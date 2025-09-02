/**
 * Import function triggers from their respective submodules:
 *
 * const {onCall} = require("firebase-functions/v2/https");
 * const {onDocumentWritten} = require("firebase-functions/v2/firestore");
 *
 * See a full list of supported triggers at https://firebase.google.com/docs/functions
 */

const {setGlobalOptions} = require("firebase-functions");
const {onRequest} = require("firebase-functions/https");
const logger = require("firebase-functions/logger");
const axios = require("axios");

// For cost control, you can set the maximum number of containers that can be
// running at the same time. This helps mitigate the impact of unexpected
// traffic spikes by instead downgrading performance. This limit is a
// per-function limit. You can override the limit for each function using the
// `maxInstances` option in the function's options, e.g.
// `onRequest({ maxInstances: 5 }, (req, res) => { ... })`.
// NOTE: setGlobalOptions does not apply to functions using the v1 API. V1
// functions should each use functions.runWith({ maxInstances: 10 }) instead.
// In the v1 API, each function can only serve one request per container, so
// this will be the maximum concurrent request count.
setGlobalOptions({ maxInstances: 10 });

// Create and deploy your first functions
// https://firebase.google.com/docs/functions/get-started

// Proxy function to redirect all requests to Cloud Run
exports.proxy = onRequest({ maxInstances: 10 }, async (req, res) => {
  try {
    const targetUrl = `https://tobedtakip-90863126066.europe-west1.run.app${req.url}`;
    
    logger.info(`Proxying request to: ${targetUrl}`);
    
    // Forward the request to Cloud Run
    const response = await axios({
      method: req.method,
      url: targetUrl,
      headers: {
        ...req.headers,
        host: 'tobedtakip-90863126066.europe-west1.run.app'
      },
      data: req.body,
      validateStatus: () => true, // Don't throw on HTTP error status codes
      maxRedirects: 0
    });
    
    // Forward response headers
    Object.keys(response.headers).forEach(key => {
      if (key.toLowerCase() !== 'content-encoding') {
        res.set(key, response.headers[key]);
      }
    });
    
    // Set status and send response
    res.status(response.status).send(response.data);
    
  } catch (error) {
    logger.error("Proxy error:", error);
    res.status(500).send("Proxy error occurred");
  }
});
