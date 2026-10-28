"""Additional Dart declaration detail from the bundled grammar; no evaluation."""
import re


def dart_details(symbol):
    from tree_sitter import Parser
    from .syntax import grammar
    raw=symbol.source.encode('utf-8');root=Parser(grammar('dart')).parse(raw).root_node
    if root.has_error:return {'detail_warning':'Dart declaration details unavailable for this fragment.'}
    text=lambda node:raw[node.start_byte:node.end_byte].decode('utf-8')
    if symbol.kind!='class':
        signature=next((n for n in root.named_children if n.type in {'function_signature','method_signature'}),None)
        return {'signature':' '.join(text(signature).split())} if signature else {}
    node=next((n for n in root.named_children if n.type in {'class_definition','mixin_declaration','enum_declaration','extension_declaration'}),None)
    if node is None:return {}
    body=next((n for n in node.named_children if n.type in {'class_body','enum_body'}),None)
    fields=[];constructors=[];bases=[];values=[]
    for child in node.named_children:
        if child.type in {'superclass','interfaces','mixins'}:
            bases.append(re.sub(r'^(extends|implements|with)\s+','',text(child)))
    if body:
        for child in body.named_children:
            if child.type=='enum_constant':
                name=child.child_by_field_name('name')
                if name:values.append(text(name))
                continue
            if child.type!='declaration':continue
            initialized=next((n for n in child.named_children if n.type=='initialized_identifier_list'),None)
            if initialized:
                prefix=raw[child.start_byte:initialized.start_byte].decode('utf-8')
                annotation=re.sub(r'\b(final|const|late|static|var|covariant|external)\b','',prefix).strip() or 'inferred (initializer not evaluated)'
                for value in initialized.named_children:
                    name=next((n for n in value.named_children if n.type=='identifier'),None)
                    if name:fields.append({'name':text(name),'annotation':annotation})
            else:
                for value in child.named_children:
                    if 'constructor_signature' in value.type:constructors.append(' '.join(text(value).split()))
    return {'fields':fields,'bases':bases,'constructors':constructors,'enum_values':values,
            'declaration_kind':{'enum_declaration':'enum','mixin_declaration':'mixin','extension_declaration':'extension'}.get(node.type,'class')}
