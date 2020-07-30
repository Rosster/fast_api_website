/**
 * From: https://cwestblog.com/2014/03/14/javascript-getting-all-text-nodes/
 * Gets an array of the matching text nodes contained by the specified element.
 * @param  {!Element} elem
 *     The DOM element which will be traversed.
 * @param  {function(!Node,!Element):boolean} opt_fnFilter
 *     Optional function that if a true-ish value is returned will cause the
 *     text node in question to be added to the array to be returned from
 *     getTextNodesIn().  The first argument passed will be the text node in
 *     question while the second will be the parent of the text node.
 * @return {!Array.<!Node>}
 *     Array of the matching text nodes contained by the specified element.
 */
function getTextNodesIn(elem, opt_fnFilter) {
  var textNodes = [];
  if (elem) {
    for (var nodes = elem.childNodes, i = nodes.length; i--;) {
      var node = nodes[i], nodeType = node.nodeType;
      if (nodeType == 3) {
        if (!opt_fnFilter || opt_fnFilter(node, elem)) {
          textNodes.push(node);
        }
      }
      else if (nodeType == 1 || nodeType == 9 || nodeType == 11) {
        textNodes = textNodes.concat(getTextNodesIn(node, opt_fnFilter));
      }
    }
  }
  return textNodes;
}

// Change straight quotes to curly and double hyphens to em-dashes.
// From: https://leancrew.com/all-this/2010/11/smart-quotes-in-javascript/
function smarten(a) {
  a = a.replace(/(^|[-\u2014\s(\["])'/g, "$1\u2018");       // opening singles
  a = a.replace(/'/g, "\u2019");                            // closing singles & apostrophes
  a = a.replace(/(^|[-\u2014/\[(\u2018\s])"/g, "$1\u201c"); // opening doubles
  a = a.replace(/"/g, "\u201d");                            // closing doubles
  a = a.replace(/--/g, "\u2014");                           // em-dashes
  return a
}


function random_id() {
    return '_' + Math.random().toString(36).substr(2, 9);
}

class FineArt {
    constructor (el) {
        this.el = el;
        this.art_type = el.dataset.art_type;

        this.image_id = null;
    }

    get random_art() {
        return this.request_random_art()
    }

    async request_random_art() {
        let url = '/random_art';
        if (this.art_type) {
            url = url + `?art_type=${this.art_type}`
        }
        return fetch(url,
            {credentials: 'same-origin'}).then(o => {
            return o.json()
        })
    }

    build_html(art_object) {
        this.image_id = random_id();

        return `<label for="art-${this.image_id}" class="margin-toggle">⌬</label><input type="checkbox" id="art-${this.image_id}" class="margin-toggle">
<span class="marginnote">${art_object.artistDisplayName || art_object.culture}, <em>${art_object.title}</em>, ${art_object.objectDate || "Unknown Date"}.</span>
          <img src="${art_object.primaryImageSmall}" alt="${encodeURIComponent(art_object.title)}, ${encodeURIComponent(art_object.artistDisplayName)}">`;
    };

    draw(el){
        this.random_art.then(art_object=>{
            this.el.innerHTML = this.build_html(art_object);
        })
    }
}

window.onload = function () {

    for (let node of getTextNodesIn(document)) {
        node.textContent = smarten(node.textContent);
    }
};

document.addEventListener("DOMContentLoaded", function(event) {
    for (let el of document.getElementsByTagName('figure')){
        if (el.classList.contains('art-fill')){
            let art = new FineArt(el);
            art.draw();
        }
    }

});