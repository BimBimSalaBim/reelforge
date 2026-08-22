/* Screenshots chosen before the job exists.
 *
 * The job id is only minted on create, so files are held here with their crop
 * and placement and committed afterwards. The sequencing is load-bearing and
 * matches what the v1 form worked out the hard way: create the job stopped,
 * upload, PATCH each image, and only then start it -- because the storyboard
 * picks one screenshot layout per image, so an image that lands after the
 * storyboard has run never appears in the reel.
 */
(function (RF) {
  "use strict";

  var items = [];
  var nextId = 1;

  function add(files, role) {
    var spec = RF.spec.get();
    var added = [], rejected = [];
    var work = Array.prototype.map.call(files, function (file) {
      var problem = RF.spec.checkFile(file);
      if (problem) { rejected.push({ name: file.name, reason: problem }); return null; }
      return measure(file).then(function (size) {
        var fit = RF.spec.defaultFit(size.w, size.h);
        var item = {
          uid: "s" + (nextId++), file: file, role: role || "other",
          objectUrl: size.url, srcW: size.w, srcH: size.h,
          fit: fit, position: "bottom", caption: "",
          crop: RF.spec.defaultCrop(size.w, size.h, fit),
        };
        items.push(item); added.push(item);
      }).catch(function () {
        rejected.push({ name: file.name, reason: "could not be read as an image" });
      });
    }).filter(Boolean);

    return Promise.all(work).then(function () {
      return { added: added, rejected: rejected };
    });
  }

  /* decode() rather than createImageBitmap: the bitmap keeps a second full-size
   * copy per file in memory, which with eight 12 MB screenshots is a spike for
   * nothing -- all we need is naturalWidth/Height. */
  function measure(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var probe = new Image();
      probe.onload = function () {
        resolve({ w: probe.naturalWidth, h: probe.naturalHeight, url: url });
      };
      probe.onerror = function () { URL.revokeObjectURL(url); reject(new Error("bad image")); };
      probe.src = url;
    });
  }

  function remove(uid) {
    items = items.filter(function (item) {
      if (item.uid !== uid) return true;
      URL.revokeObjectURL(item.objectUrl);
      return false;
    });
  }

  function all() { return items.slice(); }
  function count() { return items.length; }
  function clear() {
    items.forEach(function (item) { URL.revokeObjectURL(item.objectUrl); });
    items = [];
  }

  /* One file per request, deliberately. `upload_images` returns
   * {added, problems} and when a file is rejected the `added` array no longer
   * lines up with what was sent -- a positional match would silently attach one
   * screenshot's crop to another. One at a time makes the mapping exact. */
  function commit(jobId, onStep) {
    var queue = all();
    var uploaded = [], failed = [];

    return queue.reduce(function (chain, item, index) {
      return chain.then(function () {
        if (onStep) onStep(index + 1, queue.length, item);
        var form = new FormData();
        form.append("files", item.file, item.file.name);
        return RF.api.upload(
          "/api/jobs/" + encodeURIComponent(jobId) +
          "/images?role=" + encodeURIComponent(item.role), form
        ).then(function (result) {
          var made = (result.added || [])[0];
          if (!made) throw new Error((result.problems || []).join("; ") || "upload rejected");
          return RF.api.patch(
            "/api/jobs/" + encodeURIComponent(jobId) + "/images/" + made.id,
            { fit: item.fit, position: item.position, caption: item.caption,
              crop_x: item.crop.x, crop_y: item.crop.y,
              crop_w: item.crop.w, crop_h: item.crop.h }
          );
        }).then(function (saved) {
          uploaded.push(saved);
        }).catch(function (error) {
          failed.push({ name: item.file.name, reason: error.message });
        });
      });
    }, Promise.resolve()).then(function () {
      return { uploaded: uploaded, failed: failed };
    });
  }

  window.addEventListener("beforeunload", clear);

  RF.stage = { add: add, remove: remove, all: all, count: count,
               clear: clear, commit: commit };
})(window.RF || (window.RF = {}));
