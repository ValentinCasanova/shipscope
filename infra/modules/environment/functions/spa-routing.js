// Viewer-request function on the default (S3) behavior only. Client-side routes such as
// /orders/42 have no file extension, so they get the React app's index.html and a reload
// or shared link still works. Files such as /assets/index-abc123.js or /favicon.svg go
// to S3 unchanged. API requests use other behaviors, so API errors never reach this.
function handler(event) {
  var request = event.request;
  var lastSegment = request.uri.split('/').pop();
  if (lastSegment.indexOf('.') === -1) {
    request.uri = '/index.html';
  }
  return request;
}
