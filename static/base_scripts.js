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
      if (nodeType === 3) {
        if (!opt_fnFilter || opt_fnFilter(node, elem)) {
          textNodes.push(node);
        }
      }
      else if (nodeType === 1 || nodeType === 9 || nodeType === 11) {
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


function image_load(el) {
    if (el.parentElement.classList.contains('header-image-preload')) {
        el.parentElement.classList.remove('header-image-preload');
    }
}


class SpaceImage {
    // Thanks to our friends at NASA! https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf
    constructor (el) {
        this.el = el;
        this.image_type = el.dataset.image_type;
        this.image_id = null;
        this.n_tries = 0;
    }

    async search_for_images(page) {
        let url = `https://images-api.nasa.gov/search?q=${encodeURIComponent(this.image_type || 'nebula')}`;
        if (page && page > 0) {
            url = url + `&page=${page}`
        }

        return fetch(url, {mode:'cors'})
            .then(o => {
                return o.json()
            })
            .catch(err => console.log(err))
    }


    parse_item(item_obj) {
        let preview = item_obj.links.filter(li => li.rel === 'preview');
        let preview_image = null;
        if (preview.length) {
            preview_image = preview[0].href;
        }
        let data = null;
        if (item_obj.data.length) {
            data = item_obj.data[0];
        }
        return {
            data: data,
            preview_href: preview_image
        }
    }

    async get_random_image() {
        return this.search_for_images().then(o => {
            let total_results = o.collection.metadata.total_hits;
            let page = parseInt(Math.random()*total_results/100)
            if (page > 1) {
                this.search_for_images(page).then(o => {
                    return this.parse_item(
                        o.collection.items[Math.floor(Math.random()*o.collection.items.length)]);
                })
            } else {
                return this.parse_item(
                        o.collection.items[Math.floor(Math.random()*o.collection.items.length)]);
            }
        });
    }

    build_html(image_data) {
        this.image_id = random_id();

        return `<label for="art-${this.image_id}" class="margin-toggle">⌬</label><input type="checkbox" id="art-${this.image_id}" class="margin-toggle">
<span class="marginnote">${image_data.data.secondary_creator || image_data.data.center}, <em>${image_data.data.title}</em>, ${image_data.data.date_created}.</span>
          <img src="${image_data.preview_href}" alt="${encodeURIComponent(image_data.data.title)}">`;
    }

    draw () {
        if (this.n_tries > 10) {
            console.log(`The api is struggling, tried ${this.n_tries} times, to no avail!`);
            return
        }
        this.get_random_image().then(image_data=>{
            if (!image_data){
                this.n_tries ++;
                let cls = this;
                return setTimeout(function(){
                    cls.draw();},
            500);
            }
            this.el.innerHTML = this.build_html(image_data);
        })
    }
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
        return `<label for="art-${this.image_id}" class="margin-toggle">⌬</label>
<input type="checkbox" id="art-${this.image_id}" class="margin-toggle">
<span class="marginnote">${art_object.artistDisplayName || art_object.culture}, 
<em>${art_object.title}</em>, 
${art_object.objectDate || "Unknown Date"}.
</span>
          <img src="${art_object.primaryImageSmall}" alt="${encodeURIComponent(art_object.title)}, ${encodeURIComponent(art_object.artistDisplayName)}" onload="image_load(this)">`;
    };

    draw(){
        this.random_art.then(art_object=>{
            this.el.innerHTML = this.build_html(art_object);
        })
    }
}

// From here: https://stackoverflow.com/questions/8729193/how-to-get-all-parent-nodes-of-given-element-in-pure-javascript
const parents = node => (node.parentElement ? parents(node.parentElement) : []).concat([node]);

hljs.initHighlightingOnLoad();

window.onload = function () {
    for (let node of getTextNodesIn(document)) {
        let parent_tags = parents(node).map(p => p ? p.tagName : null);
        if (!parent_tags.includes('CODE')){
            node.textContent = smarten(node.textContent);
        }
    }
};

document.addEventListener("DOMContentLoaded", function() {
    for (let el of document.getElementsByTagName('figure')){
        if (el.classList.contains('art-fill')){
            let art = new FineArt(el);
            art.draw();
        } else if (el.classList.contains('space-fill')) {
            let space = new SpaceImage(el);
            space.draw();
        }
    }

});