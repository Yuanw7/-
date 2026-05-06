import { X, RefreshCw } from 'lucide-react';
import { UploadedImage } from '../types';

interface ImagePreviewProps {
  image: UploadedImage;
  onRemove: () => void;
  onReset: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

export default function ImagePreview({ image, onRemove, onReset }: ImagePreviewProps) {
  return (
    <div className="w-full max-w-2xl mx-auto animate-scale-in">
      <div className="relative bg-white/80 backdrop-blur-sm rounded-2xl shadow-lg overflow-hidden border border-white/50">
        <div className="flex items-center gap-4 p-4">
          <div className="relative w-24 h-24 rounded-xl overflow-hidden flex-shrink-0 group">
            <img
              src={image.preview}
              alt="Preview"
              className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
            />
          </div>

          <div className="flex-1 min-w-0">
            <p className="font-medium text-slate-800 truncate">{image.file.name}</p>
            <p className="text-sm text-slate-400 mt-1">
              {formatFileSize(image.file.size)} • {image.file.type.split('/')[1].toUpperCase()}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onReset}
              className="p-2 rounded-lg bg-slate-100 hover:bg-slate-200 transition-colors"
              title="重新上传"
            >
              <RefreshCw className="w-5 h-5 text-slate-600" />
            </button>
            <button
              onClick={onRemove}
              className="p-2 rounded-lg bg-red-50 hover:bg-red-100 transition-colors"
              title="移除图片"
            >
              <X className="w-5 h-5 text-red-500" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
