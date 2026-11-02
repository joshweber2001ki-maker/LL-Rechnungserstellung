/**
 * L&L Rechnungsbrücke – Google Apps Script Web App
 *
 * Deployment (einmalig, unter finance@lockerundlauter.com):
 *   1. script.google.com → Neues Projekt „LL Rechnungsbrücke" → diesen Code einfügen.
 *   2. Projekteinstellungen → Skript-Eigenschaften: SECRET = <langer Zufallsstring>
 *   3. Bereitstellen → Neue Bereitstellung → Typ „Web-App", Ausführen als „Ich", Zugriff „Jeder".
 *   4. Web-App-URL + SECRET in config/bridge.yaml eintragen.
 *
 * Alle Aufrufe: POST mit JSON-Body {secret, action, ...}. Antwort JSON {ok, ...} oder {ok:false, error}.
 * Die Brücke sendet NIE Mails – sie legt nur Entwürfe an.
 */

var ROOT_FINANZEN = '188XnxRQFqdpcLZ-Vy3yKXegvaujrVujV'; // Locker & Lauter Finanzen

function doPost(e) {
  var out;
  try {
    var req = JSON.parse(e.postData.contents);
    var secret = PropertiesService.getScriptProperties().getProperty('SECRET');
    if (!secret || req.secret !== secret) throw new Error('unauthorized');
    switch (req.action) {
      case 'ping':      out = { ok: true, user: Session.getEffectiveUser().getEmail(), time: new Date().toISOString() }; break;
      case 'sheet':     out = readSheet(req); break;
      case 'upload':    out = upload(req); break;
      case 'draft':     out = draft(req); break;
      case 'find':      out = find(req); break;
      case 'list':      out = list(req); break;
      case 'append':    out = appendRows(req); break;
      case 'replace':   out = replaceRows(req); break;
      case 'trash':     out = trash(req); break;
      default: throw new Error('unknown action: ' + req.action);
    }
  } catch (err) {
    out = { ok: false, error: String(err && err.message || err) };
  }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}

/** {spreadsheetId, tabs:[name,...]} → {ok, tabs:{name:[[...],...]}} (Anzeigewerte, wie im Sheet sichtbar) */
function readSheet(req) {
  var ss = SpreadsheetApp.openById(req.spreadsheetId);
  var result = {};
  (req.tabs || ss.getSheets().map(function (s) { return s.getName(); })).forEach(function (name) {
    var sh = ss.getSheetByName(name);
    if (!sh) throw new Error('tab not found: ' + name);
    result[name] = sh.getDataRange().getDisplayValues();
  });
  return { ok: true, tabs: result };
}

/** {path:['Rechnungskopien','2026','November'] | folderId, filename, base64, mimeType, replace?} → {ok, id, url} */
function upload(req) {
  var folder = req.folderId ? DriveApp.getFolderById(req.folderId) : ensurePath(req.path || []);
  if (req.replace) {
    var it = folder.getFilesByName(req.filename);
    while (it.hasNext()) it.next().setTrashed(true);
  }
  var blob = Utilities.newBlob(Utilities.base64Decode(req.base64), req.mimeType || 'application/pdf', req.filename);
  var file = folder.createFile(blob);
  return { ok: true, id: file.getId(), url: file.getUrl(), folderId: folder.getId() };
}

/** Ordnerkette unter ROOT_FINANZEN anlegen/finden */
function ensurePath(path) {
  var folder = DriveApp.getFolderById(ROOT_FINANZEN);
  path.forEach(function (name) {
    var it = folder.getFoldersByName(name);
    folder = it.hasNext() ? it.next() : folder.createFolder(name);
  });
  return folder;
}

/** {to:[...], cc:[...], subject, html, text, attachments:[{filename, base64, mimeType}]} → {ok, draftId} */
function draft(req) {
  var atts = (req.attachments || []).map(function (a) {
    return Utilities.newBlob(Utilities.base64Decode(a.base64), a.mimeType || 'application/pdf', a.filename);
  });
  var opts = { attachments: atts };
  if (req.html) opts.htmlBody = req.html;
  if (req.cc && req.cc.length) opts.cc = req.cc.join(',');
  var d = GmailApp.createDraft((req.to || []).join(','), req.subject || '', req.text || '', opts);
  return { ok: true, draftId: d.getId(), messageId: d.getMessage().getId() };
}

/** {name, parentId?, mimeType?} → {ok, files:[{id,name,parents:[names up to root]}]} – z. B. Kampagnenordner „06_Rechnungen" */
function find(req) {
  var q = "title = '" + String(req.name).replace(/'/g, "\\'") + "' and trashed = false";
  if (req.mimeType) q += " and mimeType = '" + req.mimeType + "'";
  var files = [];
  var it = req.mimeType === 'application/vnd.google-apps.folder' || !req.mimeType ? DriveApp.searchFolders(q) : DriveApp.searchFiles(q);
  while (it.hasNext() && files.length < 50) {
    var f = it.next();
    files.push({ id: f.getId(), name: f.getName(), url: f.getUrl(), parents: parentChain(f) });
  }
  return { ok: true, files: files };
}

function parentChain(f) {
  var names = [], p = f.getParents(), depth = 0;
  while (p.hasNext() && depth < 8) { var par = p.next(); names.push(par.getName()); p = par.getParents(); depth++; }
  return names;
}

/** {folderId} → {ok, folders:[{id,name}], files:[{id,name,size}]} */
function list(req) {
  var folder = DriveApp.getFolderById(req.folderId);
  var folders = [], files = [];
  var fi = folder.getFolders(); while (fi.hasNext()) { var d = fi.next(); folders.push({ id: d.getId(), name: d.getName() }); }
  var ff = folder.getFiles(); while (ff.hasNext()) { var x = ff.next(); files.push({ id: x.getId(), name: x.getName(), size: x.getSize(), url: x.getUrl() }); }
  return { ok: true, folders: folders, files: files };
}

/** {spreadsheetId, tab?, rows:[[...],...]} → Zeilen anhängen (Register-Spiegel); ohne tab: erstes Blatt */
function appendRows(req) {
  var ss = SpreadsheetApp.openById(req.spreadsheetId);
  var sh = req.tab ? ss.getSheetByName(req.tab) : ss.getSheets()[0];
  if (!sh) throw new Error('tab not found: ' + req.tab);
  if (req.rows && req.rows.length) sh.getRange(sh.getLastRow() + 1, 1, req.rows.length, req.rows[0].length).setValues(req.rows);
  return { ok: true, appended: (req.rows || []).length };
}

/** {spreadsheetId, tab?, rows:[[...],...]} → Blatt komplett ersetzen (Register-Spiegel = Abbild der CSV im Repo) */
function replaceRows(req) {
  var ss = SpreadsheetApp.openById(req.spreadsheetId);
  var sh = req.tab ? ss.getSheetByName(req.tab) : ss.getSheets()[0];
  if (!sh) throw new Error('tab not found: ' + req.tab);
  sh.clearContents();
  if (req.rows && req.rows.length) {
    var width = Math.max.apply(null, req.rows.map(function (r) { return r.length; }));
    var rows = req.rows.map(function (r) { while (r.length < width) r.push(''); return r; });
    sh.getRange(1, 1, rows.length, width).setValues(rows);
    sh.setFrozenRows(1);
  }
  return { ok: true, rows: (req.rows || []).length };
}

/** {fileId} → in den Papierkorb (nur für Dateien, die die Brücke selbst angelegt hat) */
function trash(req) {
  DriveApp.getFileById(req.fileId).setTrashed(true);
  return { ok: true };
}
