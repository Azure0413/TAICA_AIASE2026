function CodeBlock(block)
  if block.classes[1] == "mermaid" then
    if FORMAT:match 'html' then
      return pandoc.RawBlock('html',
        '<div class="mermaid">\n' .. block.text .. '\n</div>')
    else
      return pandoc.Para({
        pandoc.Emph({pandoc.Str("[Mermaid diagram -- see HTML version]")})
      })
    end
  end
end