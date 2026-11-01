// A Go server shown in Cornea, using only the standard library.
//
//	go run . 5104
package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"runtime"
	"strings"
)

const page = `<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Cornea: Go</title></head>
  <body>
    <h1>Hello from Go</h1>
    <p>Try <a href="/hello?name=Zed">/hello?name=Zed</a>.</p>
  </body>
</html>
`

func main() {
	port := "5104"
	if len(os.Args) > 1 {
		port = os.Args[1]
	} else if fromEnv := os.Getenv("PORT"); fromEnv != "" {
		port = fromEnv
	}

	http.HandleFunc("/hello", func(w http.ResponseWriter, r *http.Request) {
		name := r.URL.Query().Get("name")
		if name == "" {
			name = "world"
		}
		version := strings.TrimPrefix(runtime.Version(), "go")
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{
			"message": fmt.Sprintf("Hello, %s, from Go %s!", name, version),
		})
	})
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		fmt.Fprint(w, page)
	})

	fmt.Println("Listening on http://127.0.0.1:" + port)
	if err := http.ListenAndServe("127.0.0.1:"+port, nil); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
