"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "integrations/word_addin/auth_dialog.js"),
  "utf8"
);
const origin = "https://vindex.test";

function element() {
  return {
    handlers: {},
    attributes: {},
    disabled: false,
    hidden: false,
    value: "",
    textContent: "",
    addEventListener(name, handler) { this.handlers[name] = handler; },
    setAttribute(name, value) { this.attributes[name] = value; }
  };
}

function makeDialog(failed) {
  const elements = {
    "login-form": element(),
    "login-submit": element(),
    "email": element(),
    "password": element(),
    "auth-status": element()
  };
  elements.email.value = "lawyer@example.test";
  elements.password.value = "not-a-real-password";
  const messages = [];
  let parentHandler = null;
  let clientOptions = null;
  const Office = {
    AsyncResultStatus: { Succeeded:"succeeded" },
    EventType: { DialogParentMessageReceived:"parent-message" },
    context: {
      requirements: { isSetSupported: () => true },
      ui: {
        addHandlerAsync(type, handler, callback) {
          parentHandler = handler;
          callback({ status:"succeeded" });
        },
        messageParent(message, options) {
          assert.equal(options.targetOrigin, origin);
          messages.push(message);
        }
      }
    },
    onReady() { return Promise.resolve(); }
  };
  const window = {
    location: { protocol:"https:", origin },
    VindexWordAuthFlow: { parseEnvelope: JSON.parse },
    VindexAuthConfig: {
      supabaseUrl:"https://auth.example.test",
      supabaseAnonKey:"test-only-public-key"
    },
    supabase: {
      createClient(url, key, options) {
        clientOptions = { url, key, options };
        return {
          auth: {
            async signInWithPassword() {
              if (failed) return { data:null, error:{ message:"provider details must stay private" } };
              return { data:{ session:{ access_token:"a.b.c" } }, error:null };
            }
          }
        };
      }
    }
  };
  vm.runInNewContext(source, {
    window, document:{ getElementById(id) { return elements[id]; } },
    Office, Promise, Error, JSON, RegExp
  });

  return {
    elements, messages,
    get clientOptions() { return clientOptions; },
    sendChallenge() {
      parentHandler({
        origin,
        message: JSON.stringify({ type:"vindex-auth-challenge", nonce:"f".repeat(64) })
      });
    }
  };
}

async function main() {
  const failed = makeDialog(true);
  await new Promise(resolve => setImmediate(resolve));
  failed.sendChallenge();
  const failedEvent = { preventDefault() {} };
  await failed.elements["login-form"].handlers.submit(failedEvent);
  assert.equal(failed.messages.length, 1);
  assert.equal(failed.messages[0], "vindex-auth-ready");
  assert.equal(failed.elements.password.value, "");
  assert.match(failed.elements["auth-status"].textContent, /nije uspela/);
  assert.equal(failed.elements["login-submit"].disabled, false);
  assert.equal(JSON.stringify(failed.messages).includes("provider details"), false);
  assert.equal(failed.clientOptions.options.auth.persistSession, false);
  assert.equal(failed.clientOptions.options.auth.autoRefreshToken, false);
  assert.equal(failed.clientOptions.options.auth.detectSessionInUrl, false);

  const success = makeDialog(false);
  await new Promise(resolve => setImmediate(resolve));
  success.sendChallenge();
  await success.elements["login-form"].handlers.submit({ preventDefault() {} });
  assert.equal(success.messages.length, 2);
  const authResult = JSON.parse(success.messages[1]);
  assert.equal(authResult.type, "vindex-auth-result");
  assert.equal(authResult.nonce, "f".repeat(64));
  assert.equal(authResult.access_token, "a.b.c");
  assert.equal(success.elements["login-form"].hidden, true);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});