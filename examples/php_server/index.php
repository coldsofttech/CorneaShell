<?php
// A PHP server shown in Cornea, using the built-in web server.
//   php -S 127.0.0.1:5103 -t examples/php_server examples/php_server/index.php
// The last argument is the router: it sees every request, so /hello reaches this script too.

$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);

if ($path === '/hello') {
    $name = isset($_GET['name']) ? (string) $_GET['name'] : 'world';
    header('Content-Type: application/json');
    echo json_encode(['message' => "Hello, $name, from PHP " . PHP_VERSION . '!']);
} elseif ($path === '/') {
    header('Content-Type: text/html; charset=utf-8');
    ?>
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Cornea: PHP</title></head>
  <body>
    <h1>Hello from PHP</h1>
    <p>Try <a href="/hello?name=Zed">/hello?name=Zed</a>.</p>
  </body>
</html>
<?php
} else {
    http_response_code(404);
    echo 'Not found';
}
