// Viewer-request function. cdn.tf renders this template twice: with spa_routing on for
// the default (S3) behavior, and off for /api/*, /admin/*, and /static/*.
//
// The environment's domain is its only host. A request for any other host, such as the
// distribution's own d….cloudfront.net name, gets a 301 to the same path and query
// string on the domain. Google sends sign-ins back only to the domain, and Django
// accepts only that host.
//
// With spa_routing on, client-side routes such as /orders/42 have no file extension, so
// they get the React app's index.html, and a reload or a shared link still works. Files
// such as /assets/index-abc123.js or /favicon.svg go to S3 unchanged. The API behaviors
// run the function with it off, so API errors never turn into the React page.
var DOMAIN = '${domain}';
var SPA_ROUTING = ${spa_routing};

function handler(event) {
  var request = event.request;
  var host = request.headers.host ? request.headers.host.value : '';
  if (host !== DOMAIN) {
    return {
      statusCode: 301,
      statusDescription: 'Moved Permanently',
      headers: {
        location: { value: 'https://' + DOMAIN + request.uri + queryString(request.querystring) },
      },
    };
  }
  if (SPA_ROUTING && request.uri.split('/').pop().indexOf('.') === -1) {
    request.uri = '/index.html';
  }
  return request;
}

// The query string as the viewer sent it. CloudFront passes each value unchanged, so
// percent-encoded values stay encoded, and lists every value of a repeated name in
// multiValue.
function queryString(parameters) {
  var pairs = [];
  Object.keys(parameters).forEach(function (name) {
    var parameter = parameters[name];
    (parameter.multiValue || [parameter]).forEach(function (item) {
      pairs.push(name + '=' + item.value);
    });
  });
  return pairs.length ? '?' + pairs.join('&') : '';
}
