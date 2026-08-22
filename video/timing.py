"""Loader for build/<name>.timing.json -- the storyboard's clock."""
import json, os
HERE=os.path.dirname(os.path.abspath(__file__))
class Timing:
    def __init__(self,name):
        with open(os.path.join(HERE,"build",f"{name}.timing.json")) as fh:
            d=json.load(fh)
        self.duration=d["duration"]; self.words=d["words"]
        self.segments=[tuple(x) for x in d["segments"]]; self.phrases=d["phrases"]
    def _hits(self,word):
        k=word.lower().strip('.,:;!?')
        return [x for x in self.words if x["w"].lower().strip('.,:;!?')==k]
    def ws(self,word,nth=0):
        """start time of the nth occurrence. Raises if absent -- a typo here is
        otherwise a silent mistiming."""
        h=self._hits(word)
        if len(h)<=nth: raise KeyError(f"{word!r} occurrence {nth} not in narration")
        return h[nth]["s"]
    def we(self,word,nth=0):
        h=self._hits(word)
        if len(h)<=nth: raise KeyError(f"{word!r} occurrence {nth} not in narration")
        return h[nth]["e"]
    def index(self,word,nth=0):
        """absolute index into .words -- use with care, see DEVELOPMENT.md gotcha #4"""
        k=word.lower().strip('.,:;!?')
        n=0
        for i,x in enumerate(self.words):
            if x["w"].lower().strip('.,:;!?')==k:
                if n==nth: return i
                n+=1
        raise KeyError(word)
    def chunks(self,max_words=3,max_chars=26,gap=0.16):
        """group words into caption chunks that never cross a pause"""
        out=[];cur=[]
        for i,w in enumerate(self.words):
            g=(w["s"]-self.words[i-1]["e"]) if i else 0
            txt=" ".join(x["w"] for x in cur+[w])
            if cur and (g>gap or len(cur)>=max_words or len(txt)>max_chars):
                out.append(cur); cur=[]
            cur.append(w)
        if cur: out.append(cur)
        return [{"s":c[0]["s"],"e":c[-1]["e"],"ws":c} for c in out]
