import { useState, useCallback } from 'react';
import { Upload, Image } from 'lucide-react';
import { UploadedImage } from '../types';

interface UploadZoneProps {
  onImageUpload: (image: UploadedImage) => void;
  isLoading: boolean;
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'];

export default function UploadZone({ onImageUpload, isLoading }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validateFile = (file: File): string | null => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      return '不支持的图片格式，请上传 JPG、PNG、WEBP 或 HEIC 格式';
    }
    if (file.size > MAX_FILE_SIZE) {
      return '图片大小超过 10MB 限制';
    }
    return null;
  };

  const handleFile = useCallback((file: File) => {
    const error = validateFile(file);
    if (error) {
      setError(error);
      return;
    }
    setError(null);
    const preview = URL.createObjectURL(file);
    onImageUpload({ file, preview, name: file.name });
  }, [onImageUpload]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }, [handleFile]);

  return (
    <div className="w-full max-w-2xl mx-auto">
      <label
        htmlFor="file-upload"
        className={`
          relative block w-full p-10 border-2 border-dashed rounded-2xl
          transition-all duration-300 cursor-pointer
          ${isDragging
            ? 'border-primary-start bg-purple-50 scale-[1.02]'
            : 'border-slate-200 bg-white/50 hover:border-primary-start hover:bg-white'
          }
          ${isLoading ? 'pointer-events-none opacity-60' : ''}
        `}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="flex flex-col items-center gap-4">
          <div className={`
            w-16 h-16 rounded-full flex items-center justify-center
            transition-all duration-300
            ${isDragging
              ? 'bg-gradient-to-br from-primary-start to-primary-end scale-110'
              : 'bg-slate-100'
            }
          `}>
            {isLoading ? (
              <div className="w-8 h-8 border-4 border-primary-start border-t-transparent rounded-full animate-spin" />
            ) : isDragging ? (
              <Upload className="w-8 h-8 text-white" />
            ) : (
              <Image className="w-8 h-8 text-slate-400" />
            )}
          </div>

          <div className="text-center">
            <p className="text-lg font-medium text-slate-700">
              {isLoading ? '正在分析房间...' : '上传房间照片'}
            </p>
            <p className="text-sm text-slate-400 mt-1">
              {isLoading ? '智能识别中...' : '或点击选择文件 • JPG, PNG, WEBP, HEIC (最大 10MB)'}
            </p>
          </div>
        </div>

        <input
          id="file-upload"
          type="file"
          accept={ALLOWED_TYPES.join(',')}
          onChange={handleInputChange}
          className="hidden"
          disabled={isLoading}
        />
      </label>

      {error && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-xl animate-slide-in">
          <p className="text-sm text-red-600 text-center">{error}</p>
        </div>
      )}
    </div>
  );
}
