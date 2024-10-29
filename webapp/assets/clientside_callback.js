window.dash_clientside = window.dash_clientside || {}
window.dash_clientside.clientside = {
  show_edge_info: function(selected_edges, tap_edge) {
    console.log(tap_edge)
    console.log(selected_edges)
    function check_if_selected(tap_edge) {
      for (let i = 0; i < selected_edges.length; i++) {
        if (selected_edges[i].id === tap_edge.id) {
          return true
        }
      }
      return false
    }

    let elements = []
    let visibility = "hidden"

    if (tap_edge !== undefined) {
      if (!check_if_selected(tap_edge)) {
        return [{"visibility": visibility}, elements]
      }

      const pubtator_href = "https://www.ncbi.nlm.nih.gov/research/pubtator3/publication/"
      const [node_1, node_2] = tap_edge.label.split(" (interacts with) ")

      elements.push({props: {children: `Node 1: ${node_1}`}, type: "P", namespace: "dash_html_components"})
      elements.push({props: {children: `Node 2: ${node_2}`}, type: "P", namespace: "dash_html_components"})
      elements.push({props: {children: "Evidence:"}, type: "P", namespace: "dash_html_components"})

      Object.entries(tap_edge.pmids).forEach((obj, index) => {
        const pmid = obj[0]
        const title = obj[1]
        elements.push({
          type: "P",
          namespace: "dash_html_components",
          props: {
            children: [
              `${index + 1}. `,
              {
                type: "A",
                namespace: "dash_html_components",
                props: {
                  href: pubtator_href + pmid,
                  target: "_blank",
                  children: pmid
                }
              },
              {
                type: "P",
                namespace: "dash_html_components",
                props: {
                  children: `${title}`
                }
              }
            ]
          }
        })
      })

      visibility = "visible"
    }
    console.log(elements)
    
    return [{"visibility": visibility}, elements]
  }
}