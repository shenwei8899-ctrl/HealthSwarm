import {recipeCovers} from '../data/recipe-covers.js'

// Presentation media is bound to the same immutable recipe source already authorized by the API.
export function recipeCover(dish) {
  if(dish?.image_url)return {image_url:dish.image_url,image_source:dish.image_source}
  const source=dish?.source
  if(!source)return null
  const cover=recipeCovers.find(item=>item.kb_id===source.kb_id&&item.file_id===source.file_id&&item.file_hash===source.file_hash)
  return cover?{image_url:cover.image_url,image_source:{...cover.image_source}}:null
}
