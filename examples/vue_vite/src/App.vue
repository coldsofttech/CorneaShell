<script setup>
import { onMounted, ref } from "vue";
import { control, nativeAction, windowState } from "./cornea.js";

const state = ref(null);
const output = ref("Press the button.");

const refresh = async () => {
  state.value = await windowState();
};
const toggleMaximize = async () => {
  await control(state.value.maximized ? "restore" : "maximize");
  await refresh();
};
const askTheSystem = async () => {
  output.value = JSON.stringify(await nativeAction("platform_info"), null, 2);
};

onMounted(refresh);
</script>

<template>
  <!-- Our own title bar, only when the window has no native one. -->
  <header v-if="state?.frameless" class="titlebar">
    <span class="title">{{ state.title }}</span>
    <span class="drag pywebview-drag-region" />
    <button title="Minimize" @click="control('minimize')">&#8211;</button>
    <button title="Maximize" @click="toggleMaximize">&#9633;</button>
    <button class="close" title="Close" @click="control('close')">&#10005;</button>
  </header>
  <main>
    <h1>Hello from Vue</h1>
    <p>A Vite build, served from dist/ by Cornea.</p>
    <button @click="askTheSystem">Ask the system (native action)</button>
    <pre>{{ output }}</pre>
  </main>
</template>
