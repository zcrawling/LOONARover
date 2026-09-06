"""Small lossless-token S-expression reader/writer for KiCad source artifacts."""
import re,json
def parse(text):
 tokens=iter(re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text))
 def item(t):
  if t!='(':return t
  out=[]
  for t in tokens:
   if t==')':return out
   out.append(item(t))
  raise ValueError('unclosed expression')
 return item(next(tokens))
def emit(node):return '('+' '.join(map(emit,node))+')' if isinstance(node,list) else str(node)
def child(node,key):return next((x for x in node if isinstance(x,list) and x[0]==key),None)
def children(node,key):return [x for x in node if isinstance(x,list) and x[0]==key]
def put(node,key,*values):
 old=child(node,key)
 if old is not None:node.remove(old)
 node.append([key,*map(str,values)])
def unq(s):return json.loads(s) if s.startswith('"') else s
q=lambda s:json.dumps(str(s))
