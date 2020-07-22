function random_id() {
    return '_' + Math.random().toString(36).substr(2, 9);
}

class FineArt {
    constructor (el) {
        // el should be a figure html element
        this.el = el;
        this.image_id = null;
    }

    get random_art() {
        return this.request_random_art()
    }

    async request_random_art() {
        return fetch("/random_art").then(o => {
            return o.json()
        })
    }

    build_html(art_object) {
        this.image_id = random_id();

        return `<label for="art-${this.image_id}" class="margin-toggle">⌬</label><input type="checkbox" id="art-${this.image_id}" class="margin-toggle"><span class="marginnote">${art_object.artistDisplayName || art_object.culture}, <em>${art_object.title}</em>, ${art_object.objectDate}.</span>
          <img src="${art_object.primaryImageSmall}" alt="${encodeURIComponent(art_object.title)}, ${encodeURIComponent(art_object.artistDisplayName)}">`;
    };

    draw(){
        this.random_art.then(art_object=>{
            console.log(art_object);
            this.el.innerHTML = this.build_html(art_object);
        })
    }
}

document.addEventListener("DOMContentLoaded", function(event) {
    for (let el of document.getElementsByTagName('figure')){
        if (el.classList.contains('art-fill')){
            let art = new FineArt(el);
            art.draw();
        }
    }
});