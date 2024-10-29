window.dash_clientside = window.dash_clientside || {}
window.dash_clientside.clientside = {
  show_edge_info: function (selected_edges, tap_edge, pmid_title) {
    function check_if_selected(tap_edge) {
      for (let i = 0; i < selected_edges.length; i++) {
        if (selected_edges[i].id === tap_edge.id) {
          return true
        }
      }
      return false
    }

    function get_z_index(visibility) {
      return visibility === "hidden" ? -100 : 100
    }

    let elements = []
    let visibility = "hidden"

    if (tap_edge !== undefined) {
      if (!check_if_selected(tap_edge)) {
        return [{ "visibility": visibility, "zIndex": get_z_index(visibility) }, elements]
      }

      const pubtator_href = "https://www.ncbi.nlm.nih.gov/research/pubtator3/publication/"
      const [node_1, node_2] = tap_edge.label.split(" (interacts with) ")

      elements.push({ props: { children: `Node 1: ${node_1}` }, type: "P", namespace: "dash_html_components" })
      elements.push({ props: { children: `Node 2: ${node_2}` }, type: "P", namespace: "dash_html_components" })
      // elements.push({ props: { children: "Evidence:" }, type: "P", namespace: "dash_html_components" })
      const edge_table = {
        type: "Table",
        namespace: "dash_html_components",
        props: {
          className: "table table-bordered table-striped table-sm",
          children: [
            {
              type: "Thead",
              namespace: "dash_html_components",
              props: {
                children: [
                  {
                    type: "Tr",
                    namespace: "dash_html_components",
                    props: {
                      children: [
                        {
                          type: "Th",
                          namespace: "dash_html_components",
                          props: {
                            children: "No.",
                          }
                        },
                        {
                          type: "Th",
                          namespace: "dash_html_components",
                          props: {
                            children: "PMID",
                          }
                        },
                        {
                          type: "Th",
                          namespace: "dash_html_components",
                          props: {
                            children: "Title",
                          }
                        }
                      ]
                    }
                  }
                ]
              }
            },
            {
              type: "Tbody",
              namespace: "dash_html_components",
              props: {
                children: [],
              }
            }
          ]
        }
      }

      const table_entry = edge_table.props.children[1].props.children
      tap_edge.pmids.forEach((pmid, index) => {
        const title = pmid_title[pmid]

        table_entry.push({
          type: "Tr",
          namespace: "dash_html_components",
          props: {
            children: [
              {
                type: "Td",
                namespace: "dash_html_components",
                props: {
                  children: `${index + 1}`,
                }
              },
              {
                type: "Td",
                namespace: "dash_html_components",
                props: {
                  children: {
                    type: "A",
                    namespace: "dash_html_components",
                    props: {
                      href: pubtator_href + pmid,
                      target: "_blank",
                      children: pmid,
                    }
                  }
                }
              },
              {
                type: "Td",
                namespace: "dash_html_components",
                props: {
                  children: `${title}`,
                }
              }
            ]
          }
        })
      })

      visibility = "visible"
      elements.push(edge_table)
    }


    return [{ "visibility": visibility, "zIndex": get_z_index(visibility) }, elements]
  }
}