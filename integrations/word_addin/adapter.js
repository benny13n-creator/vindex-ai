(function (root) {
  "use strict";
  var LEGACY_TOKEN_KEY = "vindex_auth_token";
  var ROAMING_CLEAR_TIMEOUT_MS = 5000;
  var applyingOperations = Object.create(null);
  var consumedOperations = Object.create(null);

  function clearLocalToken() {
    try {
      if (root.localStorage) root.localStorage.removeItem(LEGACY_TOKEN_KEY);
    } catch (error) {
      return Promise.reject(new Error("legacy_local_token_cleanup_failed"));
    }
    return Promise.resolve();
  }

  function clearRoamingToken() {
    if (typeof Office === "undefined") return Promise.resolve();
    var settings = Office.context && Office.context.roamingSettings;
    if (!settings || typeof settings.remove !== "function" || typeof settings.saveAsync !== "function") {
      return Promise.reject(new Error("legacy_roaming_token_cleanup_unavailable"));
    }
    try { settings.remove(LEGACY_TOKEN_KEY); }
    catch (error) { return Promise.reject(new Error("legacy_roaming_token_cleanup_failed")); }

    return new Promise(function (resolve, reject) {
      var settled = false;
      var timer = setTimeout(function () {
        if (settled) return;
        settled = true;
        reject(new Error("legacy_roaming_token_cleanup_timeout"));
      }, ROAMING_CLEAR_TIMEOUT_MS);
      try {
        settings.saveAsync(function (result) {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          if (result && Office.AsyncResultStatus &&
              result.status === Office.AsyncResultStatus.Succeeded) resolve();
          else reject(new Error("legacy_roaming_token_cleanup_failed"));
        });
      } catch (error) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(new Error("legacy_roaming_token_cleanup_failed"));
      }
    });
  }

  async function readSelectedText(wordApi) {
    var api = wordApi || root.Word;
    if (!api || typeof api.run !== "function") {
      throw new Error("word_selection_unavailable");
    }
    return api.run(async function (context) {
      var range = context.document.getSelection();
      if (!range || typeof range.load !== "function") {
        throw new Error("word_selection_unavailable");
      }
      range.load("text");
      await context.sync();
      if (typeof range.text !== "string") {
        throw new Error("word_selection_unavailable");
      }
      return range.text;
    });
  }

  function supportsSafeRewrite(wordApi) {
    var office = root.Office;
    var requirements = office && office.context && office.context.requirements;
    if (!wordApi || typeof wordApi.run !== "function" || !requirements ||
        typeof requirements.isSetSupported !== "function") return false;
    try {
      return requirements.isSetSupported("WordApi", "1.5") &&
        requirements.isSetSupported("WordApiDesktop", "1.4");
    } catch (error) { return false; }
  }

  function requireSafeRewrite(wordApi) {
    if (!supportsSafeRewrite(wordApi)) throw new Error("word_rewrite_capability_unavailable");
  }

  async function readSelectionSnapshot(wordApi) {
    var api = wordApi || root.Word;
    requireSafeRewrite(api);
    return api.run(async function (context) {
      var range = context.document.getSelection();
      range.load("text,start,end,storyType");
      await context.sync();
      if (typeof range.text !== "string" || !Number.isInteger(range.start) ||
          !Number.isInteger(range.end) || typeof range.storyType !== "string") {
        throw new Error("word_selection_snapshot_unavailable");
      }
      return {
        text:range.text,
        start:range.start,
        end:range.end,
        storyType:range.storyType
      };
    });
  }

  function _readListType(range) {
    var format = range.listFormat;
    if (!format || typeof format.load !== "function") throw new Error("word_format_check_unavailable");
    format.load("listType");
    return format;
  }

  function _requireUniformTextFormatting(font, style) {
    var values = [font.bold, font.italic, font.underline, font.name, font.size, font.color, font.highlightColor];
    if (typeof style !== "string" || !style || values.some(function (value) {
      return value === null || typeof value === "undefined";
    })) throw new Error("word_format_unsupported");
  }

  async function applyApprovedRewrite(snapshot, replacement, wordApi) {
    var api = wordApi || root.Word;
    requireSafeRewrite(api);
    if (!snapshot || typeof snapshot.operationId !== "string" || !snapshot.operationId ||
        typeof snapshot.text !== "string" || !snapshot.text ||
        !Number.isInteger(snapshot.start) || !Number.isInteger(snapshot.end) ||
        typeof replacement !== "string" || !replacement || replacement.length > 4000) {
      throw new Error("word_rewrite_request_invalid");
    }
    var operationId = snapshot.operationId;
    if (applyingOperations[operationId] || consumedOperations[operationId]) {
      throw new Error("word_rewrite_already_applied");
    }
    applyingOperations[operationId] = true;
    var mutationSubmitted = false;
    try {
      await api.run(async function (context) {
        var document = context.document;
        var range = document.getSelection();
        range.load("text,start,end,storyType,style");
        document.load("changeTrackingMode");
        var table = range.parentTableOrNullObject;
        table.load("isNullObject");
        var tables = range.tables;
        tables.load("items/rowCount");
        var parentContentControl = range.parentContentControlOrNullObject;
        parentContentControl.load("isNullObject");
        var fields = range.fields;
        fields.load("items/code");
        var footnotes = range.footnotes;
        footnotes.load("items/id");
        var endnotes = range.endnotes;
        endnotes.load("items/id");
        var revisions = range.revisions;
        revisions.load("items/type");
        var paragraphs = range.paragraphs;
        paragraphs.load("items/text");
        var listFormat = _readListType(range);
        var font = range.font;
        font.load("bold,italic,underline,name,size,color,highlightColor");

        await context.sync();

        if (range.text !== snapshot.text || range.start !== snapshot.start || range.end !== snapshot.end ||
            range.storyType !== snapshot.storyType) {
          throw new Error("word_selection_stale");
        }
        if (range.storyType !== "MainText") throw new Error("word_story_unsupported");
        if (table.isNullObject !== true || tables.items.length) throw new Error("word_table_selection_unsupported");
        if (parentContentControl.isNullObject !== true) throw new Error("word_content_control_unsupported");
        if (fields.items.length) throw new Error("word_field_selection_unsupported");
        if (footnotes.items.length || endnotes.items.length) throw new Error("word_notes_selection_unsupported");
        if (document.changeTrackingMode !== "Off") throw new Error("word_tracked_changes_unsupported");
        if (revisions.items.length) throw new Error("word_revisions_selection_unsupported");
        if (paragraphs.items.length !== 1 || /[\r\n\t\u000b]/.test(range.text)) {
          throw new Error("word_multiline_selection_unsupported");
        }
        if (["ListNoNumbering", "None", "NoNumbering"].indexOf(listFormat.listType) < 0) {
          throw new Error("word_numbered_selection_unsupported");
        }
        _requireUniformTextFormatting(font, range.style);

        var inserted = range.insertText(replacement, api.InsertLocation.replace);
        inserted.load("text");
        mutationSubmitted = true;
        consumedOperations[operationId] = true;
        await context.sync();
        if (inserted.text !== replacement) throw new Error("word_rewrite_result_unconfirmed");
      });
      return { applied:true };
    } catch (error) {
      if (mutationSubmitted) consumedOperations[operationId] = true;
      throw error;
    } finally {
      delete applyingOperations[operationId];
    }
  }

  function clearLegacyAuthToken() {
    return clearLocalToken().then(clearRoamingToken);
  }

  var api = {
    clearLegacyAuthToken:clearLegacyAuthToken,
    readSelectedText:readSelectedText,
    supportsSafeRewrite:supportsSafeRewrite,
    readSelectionSnapshot:readSelectionSnapshot,
    applyApprovedRewrite:applyApprovedRewrite
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.VindexAmbientAdapter = api;
})(typeof window !== "undefined" ? window : globalThis);
