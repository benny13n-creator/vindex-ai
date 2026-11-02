"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.Office = {
  context: {
    requirements: {
      isSetSupported(name, version) {
        return name === "WordApi" && version === "1.5" ||
          name === "WordApiDesktop" && version === "1.4";
      }
    }
  }
};

const adapter = require(path.resolve(__dirname, "../integrations/word_addin/adapter.js"));

function makeRuntime(overrides = {}) {
  const state = {
    text:"Izabrana rečenica.",
    start:10,
    end:28,
    storyType:"MainText",
    isTable:false,
    contentControl:false,
    fields:0,
    footnotes:0,
    endnotes:0,
    revisions:0,
    tracking:"Off",
    listType:"ListNoNumbering",
    style:"Normal",
    font:{ bold:false, italic:false, underline:"None", name:"Arial", size:11, color:"#000000", highlightColor:"#FFFFFF" },
    writes:0,
    ...overrides
  };
  let queuedText = null;
  const range = {
    get text() { return state.text; },
    get start() { return state.start; },
    get end() { return state.end; },
    get storyType() { return state.storyType; },
    get style() { return state.style; },
    load() {},
    parentTableOrNullObject:{ get isNullObject() { return !state.isTable; }, load() {} },
    tables:{ get items() { return state.isTable ? [{ rowCount:1 }] : []; }, load() {} },
    parentContentControlOrNullObject:{ get isNullObject() { return !state.contentControl; }, load() {} },
    fields:{ get items() { return Array.from({length:state.fields}, (_, index) => ({ code:"FIELD" + index })); }, load() {} },
    footnotes:{ get items() { return Array.from({length:state.footnotes}, (_, index) => ({ id:index + 1 })); }, load() {} },
    endnotes:{ get items() { return Array.from({length:state.endnotes}, (_, index) => ({ id:index + 1 })); }, load() {} },
    revisions:{ get items() { return Array.from({length:state.revisions}, (_, index) => ({ type:"Inserted", index })); }, load() {} },
    paragraphs:{ get items() { return [{ text:state.text }]; }, load() {} },
    listFormat:{ get listType() { return state.listType; }, load() {} },
    font:{
      load() {},
      get bold() { return state.font.bold; },
      get italic() { return state.font.italic; },
      get underline() { return state.font.underline; },
      get name() { return state.font.name; },
      get size() { return state.font.size; },
      get color() { return state.font.color; },
      get highlightColor() { return state.font.highlightColor; }
    },
    insertText(text, location) {
      assert.equal(location, "Replace");
      queuedText = text;
      return { load() {}, get text() { return state.text; } };
    }
  };
  const context = {
    document:{
      getSelection() { return range; },
      get changeTrackingMode() { return state.tracking; },
      load() {}
    },
    async sync() {
      if (queuedText !== null) {
        state.text = queuedText;
        state.end = state.start + queuedText.length;
        queuedText = null;
        state.writes += 1;
      }
    }
  };
  const Word = {
    InsertLocation:{ replace:"Replace" },
    run(callback) { return callback(context); }
  };
  return { state, Word };
}

async function snapshot(runtime) {
  return adapter.readSelectionSnapshot(runtime.Word);
}

async function expectNoMutation(overrides, expectedError) {
  const runtime = makeRuntime(overrides);
  const selected = await snapshot(runtime);
  selected.operationId = "op-" + expectedError;
  await assert.rejects(
    adapter.applyApprovedRewrite(selected, "Predložena formulacija.", runtime.Word),
    new RegExp(expectedError)
  );
  assert.equal(runtime.state.writes, 0, expectedError);
}

async function main() {
  const runtime = makeRuntime();
  const selected = await snapshot(runtime);
  assert.deepEqual(selected, {
    text:"Izabrana rečenica.", start:10, end:28, storyType:"MainText"
  });
  selected.operationId = "approved-1";
  const originalPrefix = "Prethodni tekst. ";
  const originalSuffix = " Sledeća rečenica.";
  const applied = await adapter.applyApprovedRewrite(selected, "Predložena formulacija.", runtime.Word);
  assert.deepEqual(applied, { applied:true });
  assert.equal(runtime.state.writes, 1);
  assert.equal(runtime.state.text, "Predložena formulacija.");
  assert.equal(originalPrefix + runtime.state.text + originalSuffix,
    "Prethodni tekst. Predložena formulacija. Sledeća rečenica.");
  await assert.rejects(
    adapter.applyApprovedRewrite(selected, "Predložena formulacija.", runtime.Word),
    /word_rewrite_already_applied/
  );
  assert.equal(runtime.state.writes, 1);

  const stale = makeRuntime();
  const staleSnapshot = await snapshot(stale);
  staleSnapshot.operationId = "stale-text";
  stale.state.text = "Tekst je izmenjen u Word-u.";
  await assert.rejects(
    adapter.applyApprovedRewrite(staleSnapshot, "Ne primenjuj.", stale.Word),
    /word_selection_stale/
  );
  assert.equal(stale.state.writes, 0);

  const moved = makeRuntime();
  const movedSnapshot = await snapshot(moved);
  movedSnapshot.operationId = "same-text-other-range";
  moved.state.start += 100;
  moved.state.end += 100;
  await assert.rejects(
    adapter.applyApprovedRewrite(movedSnapshot, "Ne menjaj drugi pasus.", moved.Word),
    /word_selection_stale/
  );
  assert.equal(moved.state.writes, 0);

  await expectNoMutation({isTable:true}, "word_table_selection_unsupported");
  await expectNoMutation({listType:"ListSimpleNumbering"}, "word_numbered_selection_unsupported");
  await expectNoMutation({footnotes:1}, "word_notes_selection_unsupported");
  await expectNoMutation({endnotes:1}, "word_notes_selection_unsupported");
  await expectNoMutation({tracking:"TrackAll"}, "word_tracked_changes_unsupported");
  await expectNoMutation({revisions:1}, "word_revisions_selection_unsupported");
  await expectNoMutation({font:{bold:null, italic:false, underline:"None", name:"Arial", size:11, color:"#000000", highlightColor:"#FFFFFF"}}, "word_format_unsupported");
  await expectNoMutation({storyType:"Footnotes"}, "word_story_unsupported");
  await expectNoMutation({text:"prvi red\ndrugi red", end:28}, "word_multiline_selection_unsupported");

  const unavailable = makeRuntime();
  const oldIsSetSupported = global.Office.context.requirements.isSetSupported;
  global.Office.context.requirements.isSetSupported = () => false;
  assert.equal(adapter.supportsSafeRewrite(unavailable.Word), false);
  await assert.rejects(adapter.readSelectionSnapshot(unavailable.Word), /word_rewrite_capability_unavailable/);
  global.Office.context.requirements.isSetSupported = oldIsSetSupported;

  const closed = makeRuntime();
  const closedSnapshot = await snapshot(closed);
  closedSnapshot.operationId = "closed-document";
  closed.Word.run = () => Promise.reject(new Error("document_closed"));
  await assert.rejects(adapter.applyApprovedRewrite(closedSnapshot, "Predlog.", closed.Word), /document_closed/);
  assert.equal(closed.state.writes, 0);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
