# ai.ebigpictures.com

Static site for the Copilot labs, built from:
- https://github.com/medyabi/Copilot-Studio-lab
- https://github.com/medyabi/Copilot-Cowork-lab
- https://github.com/medyabi/windows-local-ai-apps

Rebuild after changing a lab repo:

```bash
pip install markdown pymdown-extensions pillow   # and librsvg (rsvg-convert) for the icons
git clone https://github.com/medyabi/Copilot-Studio-lab studio
git clone https://github.com/medyabi/Copilot-Cowork-lab cowork
git clone https://github.com/medyabi/windows-local-ai-apps localai
python3 tools/build.py studio cowork localai .
```
