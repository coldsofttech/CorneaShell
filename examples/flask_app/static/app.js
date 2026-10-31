const output = document.querySelector("#output");

document.querySelector("#greet").addEventListener("click", async () => {
  const name = document.querySelector("#name").value;
  const response = await fetch(`/hello?name=${encodeURIComponent(name)}`);
  output.textContent = JSON.stringify(await response.json(), null, 2);
});
